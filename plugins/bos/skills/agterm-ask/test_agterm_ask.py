import importlib.machinery
import os
import threading
import urllib.request

mod = importlib.machinery.SourceFileLoader(
    "agterm_ask", os.path.join(os.path.dirname(__file__), "agterm-ask")).load_module()


def test_page_wraps_body_and_post_lands_answer():
    page = mod.PAGE.format(title="T", body='<input name="choice" value="a">')
    assert '<form method="post" action="/answer">' in page and 'value="a"' in page
    server = mod.make_server(page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    assert b'value="a"' in urllib.request.urlopen(url).read()
    urllib.request.urlopen(url + "answer", data=b"choice=a&choice=c&note=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82")
    assert server.answer == {"choice": ["a", "c"], "note": "привет"}
    urllib.request.urlopen(url + "answer", data=b"choice=b")  # first answer wins
    assert server.answer["choice"] == ["a", "c"]
    assert b"Answer sent" in urllib.request.urlopen(url).read()
    urllib.request.urlopen(url + "draft", data=b"choice=b&note=")
    assert server.draft == {"choice": ["b"], "note": ""}
    server.shutdown()


def _fake_ctl(tmp_path, monkeypatch, open_reply):
    """An agtermctl that logs its calls; `overlay open` answers with open_reply (exit 1 when set)."""
    log = tmp_path / "calls"
    fake = tmp_path / "agtermctl"
    fake.write_text('#!/bin/sh\necho "$*" >> %s\ncase "$*" in *"overlay open"*) %s;; esac\n'
                    % (log, 'echo "%s" >&2; exit 1' % open_reply if open_reply else "exit 0"))
    fake.chmod(0o755)
    monkeypatch.setattr(mod, "AGTERMCTL", str(fake))
    monkeypatch.setenv("AGTERM_SESSION_ID", "S1")
    body = tmp_path / "b.html"
    body.write_text("<p>x</p>")
    return log, body


def test_busy_overlay_exits_4(tmp_path, monkeypatch):
    log, body = _fake_ctl(tmp_path, monkeypatch, "error: overlay already open")
    monkeypatch.setattr("sys.argv", ["agterm-ask", str(body)])
    try:
        mod.main()
        raise AssertionError("main returned")
    except SystemExit as e:
        assert e.code == 4


def test_quiet_open_notifies(tmp_path, monkeypatch):
    log, body = _fake_ctl(tmp_path, monkeypatch, None)
    monkeypatch.setattr(mod, "overlay_open", lambda url: False)  # closed at once, nothing picked
    monkeypatch.setattr(mod, "SEEN_TIMEOUT", 0)
    monkeypatch.setattr("sys.argv", ["agterm-ask", str(body), "--title", "Cache?"])
    try:
        mod.main()
    except SystemExit:
        pass
    calls = log.read_text()
    assert "notify" in calls and "Cache?" in calls and "--target S1" in calls
