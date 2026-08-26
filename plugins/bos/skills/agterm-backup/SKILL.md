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

`agterm-backup` — `install` symlinks it into `~/.local/bin`; it also runs directly from
the skill directory:

```
agterm-backup install            # wire the capture hook into ~/.claude/settings.json + make state dirs
agterm-backup status             # coverage: which running claude panes are captured
agterm-backup restore [--dry-run] [--yes]   # after restart: resume every captured session in its pane
agterm-backup snap [--harvest]   # optional: freeze a snapshot (see "The snapshot is optional")
```

State lives in `~/.agterm-backup/` (`live/` = per-pane hook captures, `snapshots/` =
frozen backups, `snapshot.json` = latest).

## Capture

`install` registers `capture.py` on SessionStart / UserPromptSubmit / PreToolUse /
Stop. Every session then records, into `live/<pane>-<role>.json` on its own events:

- `AGTERM_SESSION_ID -> agent session_id` — the join key,
- the agent's **launch flags** (`--dangerously-skip-permissions`, `--model sonnet`, …),
  read off the agent process's argv by walking up from the hook.

Zero interaction, no injection, and it is written continuously — so a crash with no
warning costs nothing. A split pane's second agent shares the session's
`AGTERM_SESSION_ID`; live files are keyed by pane role (`left`/`right`) so they don't
collide.

Flags matter as much as the id: a session that comes back without the flag it was
launched with is not the session you had.

## Reboot workflow (the main use case)

1. `agterm-backup install` (once).
2. Reboot / update agterm.
3. `agterm-backup restore --dry-run` to review, then `agterm-backup restore`.

That is the whole procedure. There is nothing to remember to do *before* the reboot,
which is the point: the moment you need this skill is usually the moment you did not
get to prepare for it.

`restore` reads the live captures, joins them to the tree as it stands now by pane
UUID, and types the resume line into every pane that is sitting at a shell. It skips a
pane that already has an agent running (so re-running it is safe), one whose transcript
is gone from disk, and one whose pane no longer exists.

## The snapshot is optional

`snap` freezes the current map plus the full topology into `snapshots/`. `restore` does
**not** need it and a snapshot id **never** overrides a live one — a stale snapshot
resuming week-old sessions is the exact failure this design avoids. It is still worth
having for two things:

- `snap --harvest` reads a pane's scrollback for a `Session ID: <uuid>` line (printed by
  `/status`) and accepts it only if a matching transcript exists — which recovers a
  session that was running before the hook existed;
- it records the launch flags of every running agent, which fills them in for live
  records written before `capture.py` learned to capture them.

## Notes

- `restore` only injects into a pane sitting at a shell prompt; a pane already running
  an agent is skipped (so re-running restore is safe). agterm's own "restore running
  commands" setting may beat it to the punch — then every pane reports as skipped and
  there is nothing to do.
- Anything that re-enters an existing session (`--resume`/`-r` with its id, `--continue`,
  `--fork-session`; codex's `resume`/`fork`/`--last`) is stripped from the recorded
  flags. It has to be: `restore` supplies its own `--resume`, claude honours the LAST
  one, and a leftover would silently resume a different session.
- `--from-live` is accepted and ignored; it is the default behaviour now.
- On a newer agterm (v0.16+), the first-party `agtermctl session restore "<cmd>"`
  per-session override can replace the restore step entirely from within the
  SessionStart hook;
  this skill targets the installed build and stays version-independent by typing into
  the restored shell.
