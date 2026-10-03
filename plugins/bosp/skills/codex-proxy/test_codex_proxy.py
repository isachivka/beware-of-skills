"""Tests for codex-proxy: chat->responses translation, SSE handling, token refresh write-back,
and the local HTTP surface against a fake backend. No network."""
import base64
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    tmp = os.path.join(tempfile.mkdtemp(), "codex_proxy_mod.py")
    shutil.copy(os.path.join(HERE, "codex-proxy"), tmp)
    spec = importlib.util.spec_from_file_location("codex_proxy_mod", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["codex_proxy_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


cp = load()


def jwt(exp):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return "h." + payload + ".s"


def auth_file(tmp_path, access, refresh="r1"):
    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
                             "tokens": {"id_token": "i", "access_token": access,
                                        "refresh_token": refresh, "account_id": "acc"},
                             "last_refresh": "old"}))
    return str(p)


def sse(*events):
    return [("data: " + json.dumps(e) + "\n").encode() for e in events]


# ---------------------------------------------------------------- translation

def test_system_becomes_instructions_and_user_becomes_input():
    body = cp.to_responses({"model": "m", "messages": [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"}]}, "dflt", "low")
    assert body["model"] == "m"
    assert body["instructions"] == "be terse"
    assert [(i["role"], i["content"][0]["type"], i["content"][0]["text"]) for i in body["input"]] == [
        ("user", "input_text", "hi"), ("assistant", "output_text", "hello"), ("user", "input_text", "again")]
    assert body["stream"] is True and body["store"] is False
    assert body["reasoning"] == {"effort": "low"}


def test_defaults_and_effort_passthrough():
    body = cp.to_responses({"messages": [{"role": "user", "content": "x"}], "reasoning_effort": "high"},
                           "dflt", "low")
    assert body["model"] == "dflt"
    assert body["reasoning"]["effort"] == "high"
    assert body["instructions"] == ""


def test_lone_system_message_becomes_the_input():
    body = cp.to_responses({"messages": [{"role": "system", "content": "fix: гит пуш"}]}, "d", "low")
    assert body["instructions"] == ""
    assert body["input"][0]["content"][0]["text"] == "fix: гит пуш"


# ---------------------------------------------------------------- SSE

def test_text_stream_collects_deltas_and_usage():
    events = cp.sse_events(sse(
        {"type": "response.created"},
        {"type": "response.output_text.delta", "delta": "git "},
        {"type": "response.output_text.delta", "delta": "push"},
        {"type": "response.completed", "response": {"usage": {
            "input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}}))
    assert list(cp.text_stream(events)) == [
        ("delta", "git "), ("delta", "push"),
        ("done", {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5})]


def test_text_stream_raises_on_failure_and_on_truncation():
    with pytest.raises(cp.UpstreamError):
        list(cp.text_stream(cp.sse_events(sse(
            {"type": "response.failed", "response": {"error": {"message": "boom"}}}))))
    with pytest.raises(cp.UpstreamError):
        list(cp.text_stream(cp.sse_events(sse({"type": "response.output_text.delta", "delta": "x"}))))


# ---------------------------------------------------------------- auth

def test_fresh_token_is_used_as_is(tmp_path):
    path = auth_file(tmp_path, jwt(time.time() + 3600))
    assert cp.current_tokens(path)["refresh_token"] == "r1"


def test_refresh_writes_rotated_tokens_back_and_keeps_other_fields(tmp_path):
    stale = jwt(time.time() + 10)
    path = auth_file(tmp_path, stale)
    calls = []

    def post(rt):
        calls.append(rt)
        return {"access_token": jwt(time.time() + 7 * 86400), "refresh_token": "r2", "id_token": "i2"}

    auth = cp.refresh_auth(stale, path, post=post)
    on_disk = json.load(open(path))
    assert calls == ["r1"]
    assert on_disk == auth
    assert on_disk["tokens"]["refresh_token"] == "r2"
    assert on_disk["tokens"]["account_id"] == "acc"
    assert on_disk["auth_mode"] == "chatgpt"
    assert on_disk["last_refresh"] != "old"
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_refresh_is_skipped_when_someone_already_refreshed(tmp_path):
    path = auth_file(tmp_path, jwt(time.time() + 3600), refresh="r9")
    auth = cp.refresh_auth("an-older-access-token", path, post=lambda rt: pytest.fail("refreshed twice"))
    assert auth["tokens"]["refresh_token"] == "r9"


# ---------------------------------------------------------------- HTTP surface

class FakeBackend:
    def __init__(self):
        self.bodies = []

    def responses(self, body):
        self.bodies.append(body)
        return io.BytesIO(b"".join(sse(
            {"type": "response.output_text.delta", "delta": "Открой "},
            {"type": "response.output_text.delta", "delta": "PR"},
            {"type": "response.completed", "response": {"usage": {
                "input_tokens": 1, "output_tokens": 2, "total_tokens": 3}}})))

    def model_ids(self):
        return ["gpt-6-luna", "gpt-6.1-sol"]


@pytest.fixture
def server():
    srv = cp.ThreadingHTTPServer(("127.0.0.1", 0), cp.Handler)
    srv.key, srv.backend = "k", FakeBackend()
    srv.default_model, srv.default_effort = "gpt-6-luna", "low"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def call(srv, path, body=None, key="k", host=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    if host:
        headers["Host"] = host
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (srv.server_address[1], path),
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_completion(server):
    status, out = call(server, "/v1/chat/completions",
                       {"model": "gpt-6.1-sol", "messages": [{"role": "user", "content": "открой пиар"}]})
    assert status == 200
    out = json.loads(out)
    assert out["choices"][0]["message"] == {"role": "assistant", "content": "Открой PR"}
    assert out["model"] == "gpt-6.1-sol"
    assert out["usage"]["total_tokens"] == 3


def test_streaming_completion(server):
    status, out = call(server, "/v1/chat/completions",
                       {"stream": True, "stream_options": {"include_usage": True},
                        "messages": [{"role": "user", "content": "x"}]})
    assert status == 200
    datas = [l[6:] for l in out.splitlines() if l.startswith("data: ")]
    assert datas[-1] == "[DONE]"
    chunks = [json.loads(d) for d in datas[:-1]]
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == "Открой PR"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1]["usage"]["total_tokens"] == 3


def test_models(server):
    status, out = call(server, "/v1/models")
    assert status == 200
    assert [m["id"] for m in json.loads(out)["data"]] == ["gpt-6-luna", "gpt-6.1-sol"]


def test_rejects_wrong_key_and_foreign_host(server):
    assert call(server, "/v1/models", key="nope")[0] == 401
    assert call(server, "/v1/models", key=None)[0] == 401
    assert call(server, "/v1/models", host="evil.example:8723")[0] == 403
    assert server.backend.bodies == []
