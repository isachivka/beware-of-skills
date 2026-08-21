---
name: agterm-fork
description: >
  Fork the agent running in an agterm pane (Claude Code or Codex) into a sibling session:
  same workspace, same launch flags, full conversation history under a fresh session id,
  waiting at its prompt.
  The source session is untouched. Also wires a "Fork session" entry into agterm's
  custom-command palette.
when_to_use: >
  Trigger on: agterm-fork, /agterm-fork, "форкни сессию", "отпочкуй эту сессию",
  "fork this session", "продолжи это в соседней вкладке", branch the current conversation
  into a parallel session, add the fork command to the agterm palette.
allowed-tools: [Bash]
---

# agterm-fork

Only inside agterm, and only with the `agterm-backup` capture hook — that hook's live
record is where a session's own claude id comes from.

```bash
agterm-fork                      # fork the current pane
agterm-fork <pane-id> [left|right]   # fork any pane (what the palette entry calls)
agterm-fork --dry-run            # print the plan, create nothing
agterm-fork install              # wire the "Fork session" custom command
agterm-fork uninstall            # remove it
```

The plugin's `bin/` is on `PATH` inside a Claude Code session, so run it by name. What `fork` does:

1. Reads the pane out of `agtermctl tree`, refuses if no claude or codex runs there.
2. Session id: the `agterm-backup` live record, falling back to a `--resume` already in the
   pane's argv. Never guessed — no id, no fork.
3. Launch flags (`--dangerously-skip-permissions`, `--model`, …) are inherited from the
   parent's argv, minus `--resume`/`--continue`/`--fork-session`.
4. `agtermctl session new --after <pane>` — the anchor carries the workspace, so the fork
   lands next to its parent — then types `claude --resume <id> --fork-session <flags>` or,
   for codex, `codex fork <id> <flags>` (codex forks natively).
5. Stops there. **The fork gets no task**; the user opens it and drives it.

`install` writes `~/.local/bin/agterm-fork` and a managed block in
`~/.config/agterm/keymap.conf`:

```
command "Fork session" cmd+ctrl+a>f $HOME/.local/bin/agterm-fork "$AGT_SESSION_ID" "$AGT_PANE"
```

so `cmd+ctrl+a>f`, or `Ctrl-Shift-O` → "Fork session", forks whatever session the cursor is
on, no Claude
involved. The wrapper resolves the newest installed copy of the skill at call time, because
the plugin cache path carries a commit sha and would otherwise break on every update.

Focus stays where it was (`--no-select`). The fork gets its own live record, so
`agterm-backup` covers it like any other session.
