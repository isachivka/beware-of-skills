#!/usr/bin/env python3
"""agterm-backup capture hook.

Registered as a Claude Code hook (SessionStart / UserPromptSubmit / PreToolUse /
Stop). On every invocation it records the deterministic mapping

    AGTERM_SESSION_ID (the agterm pane, from env)  ->  agent session_id (from stdin)

into ~/.agterm-backup/live/<AGTERM_SESSION_ID>.json.

Contract:
- Reads the hook JSON payload from stdin; reads AGTERM_* from the environment
  (inherited from the agent process that agterm launched).
- argv[1] names the agent ("claude" or "codex"); claude is assumed when absent.
  Codex fires the same event names with the same session_id/transcript_path payload,
  so one script serves both.
- NEVER writes to stdout (a SessionStart hook's stdout is injected into the
  session as context) and ALWAYS exits 0 (a hook must never disturb the session).
- Atomic write, so a concurrent snapshot never reads a half-written file.
"""
import sys
import os
import re
import json
import time
import shlex
import tempfile
import subprocess

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def norm_flags(argv, agent):
    """argv after the binary, minus anything that re-enters an existing session.
    restore supplies its own --resume; a leftover one would win and resume the
    wrong session."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if agent == "codex":
            if a in ("resume", "fork", "--last") or UUID_RE.fullmatch(a):
                continue
        else:
            if a in ("--resume", "-r"):
                skip = True
                continue
            if a.startswith("--resume=") or a.startswith("-r="):
                continue
            if a in ("--continue", "-c", "--fork-session"):
                continue
        out.append(a)
    return out


def agent_proc(agent):
    """(pid, argv) of the agent process this hook was spawned from. Walked up the
    process tree: a hook may run under an intermediate shell. ps joins argv with
    spaces, so an argument containing one is not recovered faithfully — flags do not
    have any."""
    pid = os.getppid()
    for _ in range(6):
        if pid <= 1:
            return None, []
        try:
            out = subprocess.run(["ps", "-o", "ppid=,args=", "-p", str(pid)],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return None, []
        if not out:
            return None, []
        head, _, rest = out.partition(" ")
        try:
            ppid = int(head)
        except ValueError:
            return None, []
        try:
            argv = shlex.split(rest)
        except ValueError:
            argv = rest.split()
        if argv and os.path.basename(argv[0]) == agent:
            return pid, argv
        pid = ppid
    return None, []


def agent_argv(agent):
    return agent_proc(agent)[1]


HEADLESS = {"claude": ("-p", "--print"), "codex": ("exec",)}


def interactive(argv, agent):
    """False for a headless run — one whose session is nobody's pane to restore."""
    return not any(a in HEADLESS.get(agent, ()) for a in argv[1:])


def cwd_stale(prev, transcript_path):
    """Whether the agent's cwd must be re-read (an lsof, a few ms) for this event.
    The transcript lives under the slug of the agent's cwd and MOVES with it — a
    session that enters a worktree carries its transcript along — so an unchanged
    transcript path means an unchanged cwd."""
    return (not prev.get("agent_cwd")
            or prev.get("transcript_path") != transcript_path)


def proc_cwd(pid):
    """The real working directory of a process, or None."""
    if not pid:
        return None
    try:
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if line.startswith("n/"):
            return line[1:]
    return None


JOURNAL_KEEP = 200


def journal(path, record, prev):
    """Append the record to the pane's journal when the session id or the agent cwd
    changed; rewrite it trimmed when it grows past JOURNAL_KEEP lines."""
    same = (prev.get("claude_session_id") == record["claude_session_id"]
            and prev.get("agent_cwd") == record["agent_cwd"]
            and prev.get("agent") == record["agent"])
    if same:
        return
    line = json.dumps(record) + "\n"
    try:
        with open(path, "a") as fh:
            fh.write(line)
        with open(path) as fh:
            lines = fh.readlines()
        if len(lines) > JOURNAL_KEEP * 2:
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                fh.writelines(lines[-JOURNAL_KEEP:])
            os.replace(tmp, path)
    except Exception:
        pass


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

    agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
    target = os.path.join(live_dir, pane + "-" + role + ".json")

    # The ps walk costs a few forks, so only pay it when the answer can have
    # changed: a fresh session, or a record that predates flag capture.
    prev = {}
    try:
        with open(target) as fh:
            prev = json.load(fh)
    except Exception:
        pass
    event = data.get("source") or data.get("hook_event_name") or ""
    transcript = data.get("transcript_path") or ""
    fresh = (event == "SessionStart" or prev.get("agent") != agent
             or "resume_flags" not in prev)
    need_cwd = cwd_stale(prev, transcript)
    pid, argv = (None, [])
    if fresh or need_cwd or prev.get("claude_session_id") != sid:
        pid, argv = agent_proc(agent)
        if argv and not interactive(argv, agent):
            return
    if fresh:
        flags = norm_flags(argv[1:], agent)
    else:
        flags = prev.get("resume_flags") or []
    agent_cwd = proc_cwd(pid) if need_cwd else prev.get("agent_cwd")
    if not agent_cwd:
        agent_cwd = prev.get("agent_cwd") or None

    record = {
        "agent": agent,
        "resume_flags": flags,
        "agent_cwd": agent_cwd,
        "pane_uuid": pane,
        "workspace_id": os.environ.get("AGTERM_WORKSPACE_ID") or None,
        "window_id": os.environ.get("AGTERM_WINDOW_ID") or None,
        "pane_role": role,
        "claude_session_id": sid,
        "transcript_path": transcript,
        "cwd": data.get("cwd") or "",
        "source": event,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

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
        return
    journal(target[:-len(".json")] + ".history.jsonl", record, prev)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
