---
name: agterm-restart
description: >
  Restart every Claude Code running in agterm in place: Ctrl+C each one, read the
  "claude --resume <id>" line it prints on exit, and resume it in the same pane with its
  original launch flags. Picks up a new claude binary, settings.json env or MCP config
  without losing a conversation. Also wires a "Restart claude sessions" palette entry.
when_to_use: >
  Trigger on: agterm-restart, /agterm-restart, "restart all claude sessions", "перезапусти
  все клоды", "relaunch claude everywhere", after changing settings.json env / OTel endpoint /
  MCP servers that running sessions read only at startup, after a claude update that running
  sessions should pick up.
allowed-tools: [Bash]
---

# agterm-restart

Only inside agterm.

```bash
agterm-restart --dry-run          # list the panes it would restart, change nothing
agterm-restart                    # restart them
agterm-restart --match review     # only panes whose "workspace / session" contains "review"
agterm-restart --busy             # also panes whose status is active (interrupts the turn)
agterm-restart install            # "Restart claude sessions" in the palette, chord cmd+ctrl+a>c
agterm-restart uninstall
```

What a run does, pane by pane (primary and split panes, every open window):

1. Finds claude in `agtermctl tree`: a `claude …` foreground, a versioned binary path, or a
   `zsh -lc 'claude …; exec zsh -l'` launcher.
2. Skips a pane whose status is `active` (mid-turn) unless `--busy`, and — when run from a
   claude's Bash tool (`CLAUDECODE` set) — the pane it runs in, since it would kill itself.
3. Sends Ctrl+C pairs until the pane's foreground is no longer claude.
4. Takes the session id from the `claude --resume <id>` line claude prints on exit (falls back
   to a `--resume` in the old argv). No id → the pane is left at the shell and reported.
5. Types `claude --resume <id> <flags>`: the original flags, minus the old `--resume`,
   duplicates and the positional prompt (a launch prompt must not be replayed as a new
   message).
6. Answers claude's "resume full session as-is / from summary" question with **2**
   (`--answer-choice 1|none` to change).

The palette entry runs the same thing in an overlay on the session it fired from, held open
until a key is pressed so the report stays readable. The session under the overlay restarts
too — typing goes under an overlay.

Flag/argv parsing is shared with `agterm-fork` (loaded from the sibling skill directory).
Tests: `python3 -m pytest -q test_agterm_restart.py`.
