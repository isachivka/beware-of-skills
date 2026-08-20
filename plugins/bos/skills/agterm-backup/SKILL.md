---
name: agterm-backup
description: >
  Back up and restore agterm sessions across an app/computer restart, resuming each
  running agent session in its original pane — Claude Code (claude --resume <id>) and
  Codex (codex resume <id>). Use when
  the user wants to reboot (to apply a macOS or agterm update) without losing running
  claude sessions, to capture the current sessions, to check capture coverage, or to
  restore/resume sessions after a restart.
when_to_use: >
  Trigger on: agterm-backup, backup sessions, restore sessions, resume claude after
  reboot, "I need to reboot but don't want to lose my sessions", capture running
  claude sessions, codex sessions, agterm update without losing work, agterm-backup
  install / snap / status / restore.
allowed-tools: Bash
---

# agterm-backup

Bring your running agterm sessions — Claude Code and Codex, **resumed** — back after an
agterm or macOS restart.

Codex support rides on the same machinery: it fires the same hook events
(`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`) with the same
`session_id`/`transcript_path` payload, so one capture hook serves both. `install` wires
it into `~/.codex/config.toml`; **codex then asks you to trust the changed hooks on its
next start — pick "Trust all and continue" once, or it never runs.** A pane's live record
carries which agent wrote it, so a pane that ran claude yesterday and codex today is never
resumed with the wrong one.

## Why it works (verified against agterm source)

- agterm rebuilds the session tree on cold launch **keyed by the persisted session
  UUIDs** (`AppStore.restore(from:)`), so a pane's `AGTERM_SESSION_ID` is **stable
  across a restart**. That id is the join key.
- The "Restore running commands on restart" setting only controls whether a pane
  *re-runs its command*; the tree (workspaces/sessions/cwds, as plain shells) is
  restored regardless. So after a restart panes sit at a shell prompt and we type the
  resume command into them.
- A running Claude Code session's id can't be read from outside deterministically
  (not in env, no open fd). The reliable source is a **Claude Code hook** that
  receives the exact `session_id` on stdin. Claude Code re-reads hooks per event, so
  a newly-installed hook captures **already-running** sessions on their next activity.

## The command

`~/.claude/skills/agterm-backup/agterm-backup` (run with `/usr/bin/python3` or directly):

```
agterm-backup install            # wire the capture hook into ~/.claude/settings.json + make state dirs
agterm-backup status             # coverage: which running claude panes are captured
agterm-backup snap [--harvest]   # freeze the pane->session-id map + topology to a snapshot
agterm-backup restore [--dry-run] [--yes] [--from-live]   # after restart: type claude --resume into each pane
```

State lives in `~/.agterm-backup/` (`live/` = per-pane hook captures, `snapshots/` =
frozen backups, `snapshot.json` = latest).

## Capture, two ways

- **Durable (hooks):** `install` registers `capture.py` on SessionStart /
  UserPromptSubmit / PreToolUse / Stop. Every session then records
  `AGTERM_SESSION_ID -> claude session_id` into `live/<pane>-<role>.json` on its own
  events. Zero interaction, no injection. This is the permanent solution — future
  reboots need only `snap` then `restore`.
- **Scrollback (one-shot bonus):** `snap --harvest` reads a pane's scrollback for a
  `Session ID: <uuid>` line (printed by `/status`) and accepts it only if a matching
  transcript exists. Fills gaps for sessions that were running before the hook and are
  idle. A split pane's second claude shares the session's `AGTERM_SESSION_ID`; live
  files are keyed by pane role (`left`/`right`) so they don't collide.

## Reboot workflow (the main use case)

1. `agterm-backup install` (once).
2. Let each session tick, or run `/status` in idle claude panes. Check with
   `agterm-backup status` until coverage is complete (or accept the misses it lists).
3. `agterm-backup snap --harvest` — freeze the map.
4. Reboot / update agterm.
5. When agterm is back (panes restored as shells, same UUIDs):
   `agterm-backup restore --dry-run` to review, then `agterm-backup restore`.
   It matches each saved pane by UUID and types `claude --resume <id> <flags>` into
   it, skipping panes that aren't present or already have claude running.

## Notes

- `restore` only injects into a pane sitting at a shell prompt; a pane already running
  claude is skipped (so re-running restore is safe).
- Preserved flags (e.g. `--dangerously-skip-permissions`) are read from each pane's
  live foreground argv at `snap` time and re-applied on resume.
- On a newer agterm (v0.16+), the first-party `agtermctl session restore "<cmd>"`
  per-session override can replace step 5 entirely from within the SessionStart hook;
  this skill targets the installed build and stays version-independent by typing into
  the restored shell.
