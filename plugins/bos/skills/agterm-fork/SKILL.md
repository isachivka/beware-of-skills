---
name: agterm-fork
description: >
  Fork the current Claude Code session into a new agterm session in the same workspace:
  the fork resumes this conversation's full history under a fresh session id and takes a
  task of its own, while this session keeps going untouched.
when_to_use: >
  Trigger on: agterm-fork, /agterm-fork, "форкни сессию", "отпочкуй эту сессию",
  "fork this session", "продолжи это в соседней вкладке", branch the current conversation
  into a parallel session, hand a side-task to a copy of yourself.
allowed-tools: [Bash]
argument-hint: 'what the fork should work on'
---

# agterm-fork

Needs the `agterm-backup` capture hook — that is where a session's own claude id comes
from. No hook, no fork.

1. Resolve this session's claude id from the live record the hook keeps:
   ```bash
   rec=~/.agterm-backup/live/$AGTERM_SESSION_ID-${AGTERM_PANE:-left}.json
   sid=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["claude_session_id"])' "$rec")
   ```
   Missing file → tell the user to run `agterm-backup install`; the record appears on the
   next hook event, so retry after one more turn. Never guess a session id.
2. Create the sibling session — `--after` anchors it to this one, which carries the
   workspace, so it lands in the same workspace right next to us:
   ```bash
   id=$(agtermctl session new --after "$AGTERM_SESSION_ID" --cwd "$PWD" \
        --name "fork: <short label>" --no-select --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["id"])')
   ```
   Plain shell, not `--command`: a `--command` session dies when claude exits.
3. Boot the fork — `--fork-session` gives it a NEW id, so the two histories diverge instead
   of fighting over one transcript:
   ```bash
   agtermctl session type --target "$id" "claude --resume $sid --fork-session"$'\n'
   ```
4. Read the screen back (`agtermctl session text --target "$id" --lines 25`) until the
   prompt box is up, then type the task the user gave, same `$'\n'` to submit. A fork that
   boots with no instruction just sits there.
5. Report the session name and what it was told. Focus stays here (`--no-select`).

The fork inherits the whole conversation, so say explicitly what is now ITS job and what
stays yours — otherwise both sessions redo the same work. It also gets its own live record,
so `agterm-backup` snapshots and restores it like any other session.
