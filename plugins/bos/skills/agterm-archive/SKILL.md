---
name: agterm-archive
description: >
  Park a whole agterm workspace on disk and bring it back later — snapshot its sessions,
  order, cwds, splits and each pane's claude session id, close it, and recreate it with
  every claude resumed where it left off. For workspaces that are done for now but not
  done for good.
when_to_use: >
  Trigger on: agterm-archive, /agterm-archive, "заархивируй воркспейс", "закрой воркспейс
  но запомни", "верни воркспейс из архива", "убери проект из терминала", archive a
  workspace, restore an archived workspace, park a project.
allowed-tools: [Bash]
---

# agterm-archive

Only inside agterm. Session ids come from the `agterm-backup` capture hook — without it an
agent pane comes back as a plain shell. Claude and Codex panes are both handled; the
restore types `claude --resume <id>` or `codex resume <id>` accordingly.

```bash
agterm-archive archive [workspace]   # snapshot + close (default: active workspace)
agterm-archive list                  # what is parked
agterm-archive restore <name>        # recreate it, resume the claudes
agterm-archive drop <name>           # forget an archive
agterm-archive install               # add the palette entries (ctrl+a>a / ctrl+a>r)
agterm-archive uninstall             # remove them
```

`install` writes `~/.local/bin/agterm-archive` and a managed block in
`~/.config/agterm/keymap.conf` with two custom commands: **Archive workspace**
(`ctrl+a>a`, archives the workspace the cursor is in, passing `$AGT_WORKSPACE_ID`) and
**Restore workspace** (`ctrl+a>r`, lists archives in agterm's native fuzzy picker and
restores the pick). The wrapper resolves the newest installed copy of the skill at call
time, because the plugin cache path carries a commit sha.

The plugin's `bin/` is on `PATH` inside a Claude Code session, so run it by name.
Archives live in `~/.agterm-backup/archives/<name>.json`, the run log in
`~/.agterm-backup/archive.log` — palette commands print nowhere else.

- `archive` records every session's name, cwd, title, order, split (axis + ratio) and, per pane,
  the claude session id plus its launch flags. Then `agtermctl workspace delete`. It refuses
  to archive the workspace it is running in — that would kill the caller — and warns when a
  claude pane has no captured id. `--keep` snapshots without closing, `--force` overwrites.
- `restore` recreates the sessions in order (`session new --workspace-name … --create-workspace`),
  re-opens each split at its old ratio, and types `claude --resume <id> <flags>` into each
  pane that had one. `--no-boot` leaves plain shells; `--keep` keeps the archive file
  (otherwise a successful restore consumes it); `--force` restores into an already-open
  workspace.
- Non-claude panes come back as shells in the right cwd. Whatever process they ran is gone —
  a snapshot is not a checkpoint.

This is a separate concern from `agterm-backup`: that one covers what is currently open
across a restart, this one covers what you deliberately closed. A restored workspace is
live again, so the hook re-records it and backup picks it up from there.
