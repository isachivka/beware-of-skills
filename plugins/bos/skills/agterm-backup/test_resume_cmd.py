#!/usr/bin/env python3
"""Regression tests for the resume line agterm-backup types into a pane.

The bug these exist for: a pane launched as `claude --dangerously-skip-permissions
"<a long prompt>"` carries that prompt in its argv. Restore replayed every word of it,
unquoted — the apostrophe in "repo's" left the shell at a `quote>` continuation with the
whole command unrun, and a backtick in the prompt would have been command substitution.
"""
import importlib.util
import shutil
import sys
import tempfile
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    tmp = os.path.join(tempfile.mkdtemp(), "agterm_backup_mod.py")
    shutil.copy(os.path.join(HERE, "agterm-backup"), tmp)
    spec = importlib.util.spec_from_file_location("agterm_backup_mod", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agterm_backup_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load()
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append("%s\n  got : %s\n  want: %s" % (name, got, want))

    # the real argv that wedged a pane
    argv = ["claude", "--dangerously-skip-permissions", "You", "are", "starting", "a",
            "stream", "using", "the", "repo's", "tooling", "(see", "the", "`worktree`",
            "skill)"]
    check("prompt dropped",
          m.resume_cmd("claude", "SID", m._flags(argv, "claude")),
          "claude --resume SID --dangerously-skip-permissions")

    check("flag values kept",
          m.resume_cmd("claude", "NEW", m._flags(
              ["claude", "--model", "sonnet", "--resume", "old", "prompt"], "claude")),
          "claude --resume NEW --model sonnet")

    check("codex",
          m.resume_cmd("codex", "CID", m._flags(
              ["codex", "resume", "CID", "--dangerously-bypass-approvals-and-sandbox"],
              "codex")),
          "codex resume CID --dangerously-bypass-approvals-and-sandbox")

    # a flag value that needs quoting must come back quoted, not raw
    line = m.resume_cmd("claude", "SID", m._flags(
        ["claude", "--append-system-prompt", "mind the repo's rules"], "claude"))
    check("value quoted", line,
          "claude --resume SID --append-system-prompt 'mind the repo'\"'\"'s rules'")

    check("no duplicate flags",
          m.resume_cmd("claude", "SID", m._flags(
              ["claude", "--dangerously-skip-permissions", "--resume", "old",
               "--dangerously-skip-permissions"], "claude")),
          "claude --resume SID --dangerously-skip-permissions")

    for f in failures:
        print("FAIL " + f)
    print("%d passed, %d failed" % (5 - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
