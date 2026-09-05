#!/usr/bin/env python3
"""Tests for the live-mode-era behaviour: cd before resume, the per-pane journal and
the pre-launch record rule, and the hook ignoring headless agents."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, fname):
    tmp = os.path.join(tempfile.mkdtemp(), name + ".py")
    shutil.copy(os.path.join(HERE, fname), tmp)
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load("agterm_backup_mod", "agterm-backup")
    c = load("capture_mod", "capture.py")
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append("%s\n  got : %r\n  want: %r" % (name, got, want))

    # --- resume line: cd into the agent's own cwd first, quoted -----------------------
    check("cd before resume",
          m.resume_cmd("claude", "SID", ["--model", "sonnet"],
                       cwd="/Users/is/pets/home-app/.claude/worktrees/main-work"),
          "cd /Users/is/pets/home-app/.claude/worktrees/main-work && "
          "claude --resume SID --model sonnet")
    check("cd quoted",
          m.resume_cmd("claude", "SID", [], cwd="/Users/is/it's here"),
          "cd '/Users/is/it'\"'\"'s here' && claude --resume SID")
    check("no cwd -> no cd",
          m.resume_cmd("claude", "SID", []), "claude --resume SID")

    # --- hook: headless agents never touch a pane's record ---------------------------
    check("claude -p is headless", c.interactive(["claude", "-p", "hi"], "claude"), False)
    check("claude --print is headless",
          c.interactive(["claude", "--print", "--resume", "x"], "claude"), False)
    check("claude interactive", c.interactive(["claude", "--model", "sonnet"], "claude"), True)
    check("codex exec is headless", c.interactive(["codex", "exec", "hi"], "codex"), False)
    check("codex interactive", c.interactive(["codex", "resume", "X"], "codex"), True)

    # --- hook: the agent cwd is re-read only when the transcript moved ----------------
    check("first record reads cwd", c.cwd_stale({}, "/p/a/s.jsonl"), True)
    check("same transcript -> keep",
          c.cwd_stale({"agent_cwd": "/a", "transcript_path": "/p/a/s.jsonl"},
                      "/p/a/s.jsonl"), False)
    check("transcript moved -> re-read",
          c.cwd_stale({"agent_cwd": "/a", "transcript_path": "/p/a/s.jsonl"},
                      "/p/a-wt/s.jsonl"), True)
    check("record without cwd -> re-read",
          c.cwd_stale({"transcript_path": "/p/a/s.jsonl"}, "/p/a/s.jsonl"), True)

    # --- journal: pick the record that was current before agterm launched -------------
    launch = m.parse_ts("2026-09-05T12:06:00Z")
    old = {"claude_session_id": "OLD", "ts": "2026-09-05T11:50:00Z", "agent_cwd": "/x"}
    older = {"claude_session_id": "OLDER", "ts": "2026-09-05T09:00:00Z"}
    new = {"claude_session_id": "NEW", "ts": "2026-09-05T12:07:05Z"}
    check("live newer than launch -> last pre-launch journal entry",
          m.pick_record(new, [older, old, new], launch)["claude_session_id"], "OLD")
    check("live older than launch -> live itself",
          m.pick_record(old, [older, old], launch)["claude_session_id"], "OLD")
    check("no pre-launch entry -> live (nothing better known)",
          m.pick_record(new, [new], launch)["claude_session_id"], "NEW")
    check("no journal at all -> live",
          m.pick_record(new, [], launch)["claude_session_id"], "NEW")
    check("no launch time -> live",
          m.pick_record(new, [old], None)["claude_session_id"], "NEW")

    # --- etime parsing (locale-free agterm launch time) --------------------------------
    check("etime mm:ss", m.parse_etime("05:12"), 312)
    check("etime hh:mm:ss", m.parse_etime("01:02:03"), 3723)
    check("etime dd-hh:mm:ss", m.parse_etime("2-01:02:03"), 2 * 86400 + 3723)

    # --- --as-of parsing ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        snap = os.path.join(d, "s.json")
        with open(snap, "w") as fh:
            json.dump({"ts": "2026-09-05T12:04:01Z"}, fh)
        check("as-of snapshot file", m.parse_as_of(snap), m.parse_ts("2026-09-05T12:04:01Z"))
    check("as-of iso utc", m.parse_as_of("2026-09-05T12:04:01Z"),
          m.parse_ts("2026-09-05T12:04:01Z"))

    for f in failures:
        print("FAIL " + f)
    total = 24
    print("%d passed, %d failed" % (total - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
