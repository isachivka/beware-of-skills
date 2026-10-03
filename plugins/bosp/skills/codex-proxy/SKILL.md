---
name: codex-proxy
description: >
  Run an OpenAI-compatible Chat Completions endpoint on localhost that spends the user's
  ChatGPT/Codex subscription instead of an API key — for apps that take a Base URL, API key
  and model id (dictation post-processing, editors, scripts). Install it as an always-on
  LaunchAgent, check its status, print the key, try a request, or debug a failing app.
when_to_use: >
  Trigger on: codex-proxy, "use my Codex subscription in <app>", "OpenAI-compatible endpoint
  without an API key", "the app wants an OpenAI key", Base URL 127.0.0.1:8723, the dictation
  app's post-processing provider fails, codex-proxy install / status / key / try / uninstall.
allowed-tools: Bash
---

# codex-proxy

`codex-proxy` (on PATH via this plugin's `bin/`) serves `http://127.0.0.1:8723/v1`:

| Local                       | Upstream                                              |
| --------------------------- | ----------------------------------------------------- |
| `POST /v1/chat/completions` | `POST chatgpt.com/backend-api/codex/responses` (SSE)  |
| `GET /v1/models`            | `GET chatgpt.com/backend-api/codex/models` (`list`)   |

It authenticates with the OAuth token Codex CLI keeps in `~/.codex/auth.json`, so Codex must be
logged in **with ChatGPT** (`codex login status` → "Logged in using ChatGPT"). An API-key login
has no such token; then the app should just use the key directly.

## Commands

```bash
codex-proxy install [--port 8723] [--model gpt-6-luna] [--effort low]  # LaunchAgent local.codex-proxy
codex-proxy status       # launchd loaded? port answering? hours left on the token
codex-proxy key          # the local API key to paste into the app
codex-proxy try "текст"  # one cleanup request through the running proxy, with timing
codex-proxy uninstall
codex-proxy serve ...    # foreground, for debugging
```

`install` points launchd at the script's real path — the checkout it was run from — and at
`/usr/bin/python3` (stdlib only). Re-run it after moving the checkout or changing flags.
Log: `~/Library/Logs/codex-proxy.log`, one line per request with model, effort and seconds.

## What to give the app

- Base URL `http://127.0.0.1:8723/v1`
- API key: output of `codex-proxy key` (stored in `~/.config/codex-proxy/key`)
- Model: any slug from `/v1/models`. For short text cleanup `gpt-6-luna` at the default `low`
  effort answers in ~1.5–2 s; bigger models are slower, not better at this. The `priority`
  service tier was measured slower for such short requests and is not used.

## Behaviour worth knowing

- system/developer messages → `instructions`; user/assistant → `input`. A request with only a
  system message sends it as the input. Tools, images, `temperature`, `max_tokens` are dropped;
  `reasoning_effort` in the request overrides `--effort`.
- `stream: true` gets Chat Completions chunks and `[DONE]`; otherwise one JSON completion.
- `auth.json` is re-read per request. Within 5 minutes of expiry, or on an upstream 401, the
  proxy refreshes with the refresh token and writes the rotated tokens back atomically (mode
  0600, other fields kept) under a lock — codex keeps working off the same file.
- Requests need `Authorization: Bearer <key>` and a localhost `Host`, so a web page cannot
  drive it through the browser.

## Debugging an app that fails

1. `codex-proxy status`. Not listening → read the log; `install` again.
2. `codex-proxy try`. Works here but not in the app → the app's Base URL (must end in `/v1`),
   key or model id; the log shows whether the request even arrived.
3. Upstream 401 after a refresh → `codex login` again (the refresh token was revoked).
   Upstream 400 naming a model → the slug is not in `/v1/models` for this plan.

This uses the subscription outside the Codex client; OpenAI may change or close the backend at
any time. Tests: `python3 -m pytest plugins/bosp/skills/codex-proxy`.
