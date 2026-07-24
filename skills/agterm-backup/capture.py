#!/usr/bin/env python3
"""agterm-backup capture hook.

Registered as a Claude Code hook (SessionStart / UserPromptSubmit / PreToolUse /
Stop). On every invocation it records the deterministic mapping

    AGTERM_SESSION_ID (the agterm pane, from env)  ->  claude session_id (from stdin)

into ~/.agterm-backup/live/<AGTERM_SESSION_ID>.json.

Contract:
- Reads the hook JSON payload from stdin; reads AGTERM_* from the environment
  (inherited from the claude process that agterm launched).
- NEVER writes to stdout (a SessionStart hook's stdout is injected into the
  session as context) and ALWAYS exits 0 (a hook must never disturb the session).
- Atomic write, so a concurrent snapshot never reads a half-written file.
"""
import sys
import os
import json
import time
import tempfile


def main() -> None:
    pane = os.environ.get("AGTERM_SESSION_ID")
    if not pane:
        return  # not inside agterm: nothing to map

    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    sid = data.get("session_id")
    if not sid:
        return

    live_dir = os.path.join(os.path.expanduser("~"), ".agterm-backup", "live")
    try:
        os.makedirs(live_dir, exist_ok=True)
    except Exception:
        return

    # A split pane runs a second claude under the SAME AGTERM_SESSION_ID as the
    # main pane, so the live file must be keyed by pane role too (left/right/scratch)
    # or the two would clobber each other.
    role = os.environ.get("AGTERM_PANE") or "left"

    record = {
        "pane_uuid": pane,
        "workspace_id": os.environ.get("AGTERM_WORKSPACE_ID") or None,
        "window_id": os.environ.get("AGTERM_WINDOW_ID") or None,
        "pane_role": role,
        "claude_session_id": sid,
        "transcript_path": data.get("transcript_path") or "",
        "cwd": data.get("cwd") or "",
        "source": data.get("source") or data.get("hook_event_name") or "",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    target = os.path.join(live_dir, pane + "-" + role + ".json")
    try:
        fd, tmp = tempfile.mkstemp(dir=live_dir, prefix=".tmp-")
        with os.fdopen(fd, "w") as fh:
            json.dump(record, fh)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)  # type: ignore[name-defined]
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
