---
name: agterm-fork
description: >
  Fork the current Claude Code session into a new agterm session in the same workspace:
  the fork resumes this conversation's full history under a fresh session id, with the same
  claude launch flags, and waits at its prompt. This session keeps going untouched.
when_to_use: >
  Trigger on: agterm-fork, /agterm-fork, "форкни сессию", "отпочкуй эту сессию",
  "fork this session", "продолжи это в соседней вкладке", branch the current conversation
  into a parallel session.
allowed-tools: [Bash]
---

# agterm-fork

Only inside agterm, and only with the `agterm-backup` capture hook — that is where a
session's own claude id comes from. No hook, no fork.

1. Resolve this session's claude id from the live record the hook keeps:
   ```bash
   rec=~/.agterm-backup/live/$AGTERM_SESSION_ID-${AGTERM_PANE:-left}.json
   sid=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["claude_session_id"])' "$rec")
   ```
   Missing file → tell the user to run `agterm-backup install`; the record appears on the
   next hook event, so retry after one more turn. Never guess a session id.
2. Recover the flags this session was launched with (`--dangerously-skip-permissions`, a
   `--model`, …) — the fork must run under the same ones, or it wakes up crippled:
   ```bash
   flags=$(python3 "${CLAUDE_SKILL_DIR}/claude-args.py")
   ```
   The helper walks up the process tree to the `claude` process and strips `--resume`,
   `--continue` and `--fork-session` from its argv, keeping everything else.
3. Create the sibling session — `--after` anchors it to this one, which carries the
   workspace, so it lands in the same workspace right next to us:
   ```bash
   id=$(agtermctl session new --after "$AGTERM_SESSION_ID" --cwd "$PWD" \
        --name "fork: <short label>" --no-select --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["id"])')
   ```
   Plain shell, not `--command`: a `--command` session dies when claude exits.
4. Boot the fork — `--fork-session` gives it a NEW id, so the two histories diverge instead
   of fighting over one transcript:
   ```bash
   agtermctl session type --target "$id" "claude --resume $sid --fork-session $flags"$'\n'
   ```
5. Read the screen back (`agtermctl session text --target "$id" --lines 25`) to confirm the
   prompt box is up, then stop. **Do not type a task into the fork** — the user drives it
   themselves. Report the session name and that it is ready and waiting.

Focus stays here (`--no-select`). The fork inherits the whole conversation and gets its own
live record, so `agterm-backup` snapshots and restores it like any other session.
