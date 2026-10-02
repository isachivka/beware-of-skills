# beware-of-skills

Claude Code and Codex CLI skills for working with many agent sessions at once.

They exist because I run several Claude Code and Codex sessions side by side in
[agterm](https://github.com/umputun/agterm) all day, and the seams between them — restarts,
forks, hand-offs, reviews, memory rot — needed tooling. Installs as a plugin into Claude Code
and Codex CLI.

| Skill                             | One line                                                                                     |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| [agent-pm](#agent-pm)             | Claude as a manager that only delegates: a fleet of worker sessions, briefs, gates, recovery  |
| [peer-chat](#peer-chat)           | Claude Code and Codex talk to each other across a split pane                                 |
| [agterm-backup](#agterm-backup)   | Reboot the Mac, get every running Claude/Codex session back resumed in its pane              |
| [agterm-fork](#agterm-fork)       | Fork a live session into a sibling with the whole conversation                               |
| [agterm-restart](#agterm-restart) | Restart every running Claude in place, each resumed with its own flags                       |
| [agterm-archive](#agterm-archive) | Park a whole workspace on disk, restore it later with every agent resumed                   |
| [memory-review](#memory-review)   | Turn an agent's memory pile into one annotatable document, apply your verdicts safely       |
| [revdiff-ru](#revdiff-ru)         | Code review with everything but the code translated to Russian, line numbers intact         |
| [decomment](#decomment)           | Strip the comments an agent left that just restate the code                                 |
| [own-pr](#own-pr)                 | **alpha** — drive your own PR in the session that wrote it, by a process you edit as text     |

Requirements vary by skill and are listed per skill below; the agterm ones need
[agterm](https://github.com/umputun/agterm) on macOS, the review ones need
[revdiff](https://github.com/umputun/revdiff).

## Installation

This repo is a Claude Code plugin marketplace. The plugin you want is **bos**; a second one,
**bosp**, is a reserved slot for personal integrations and is empty.

```
/plugin marketplace add isachivka/beware-of-skills
/plugin install bos@beware-of-skills
```

Skills then invoke as `/bos:<skill>`, e.g. `/bos:agent-pm`. `/plugin update` keeps them current.

### Codex

The same two plugins ship a Codex manifest (`.codex-plugin/plugin.json`) and a Codex marketplace
(`.agents/plugins/marketplace.json`), so Codex CLI can install them from a local clone:

```
git clone https://github.com/isachivka/beware-of-skills.git
codex plugin marketplace add ./beware-of-skills
codex plugin add bos@beware-of-skills
```

Codex copies the plugin into its own cache on install, so after editing or adding a skill in the
clone, re-run `codex plugin add bos@beware-of-skills` and start a new thread to pick it up.

## Skills — `bos`

### agent-pm

Turns Claude into a **manager that does nothing itself** — it orchestrates a fleet of full Claude Code instances running in [agterm](https://github.com/umputun/agterm) sessions: one worker per repo/role, delegation with briefs, a 5-minute check loop, PM-held gates (plan/PR review, prod actions), and battle-tested recovery playbooks for degraded workers.

Born from a real production day: a frontend redesign shipped through 3 feedback iterations, a public buglash, a cross-repo fix, and an A/B experiment launch — all driven by one PM agent supervising 4 worker agents.

**Requires:** the `agterm` skill (all terminal mechanics are delegated to it) and a `claude_yolo` alias (claude with permission checks bypassed).

**Triggers:** "you are the manager", "you are the PM", "orchestrate the agents", "spin up workers", "agent-pm"

**Example:**

> *You:* You are the manager for document-restoration. You do nothing by hand — you only brief the agents through agterm and check their work.
> *Claude:* *(maps the sessions, asks who is who, and starts running the show)*

### peer-chat

Lets Claude Code and Codex talk directly across the two panes of one agterm split. A guarded helper
checks that the target pane is running the expected agent and that its composer is empty before it
types or submits anything. The skill never starts agents or answers permission and trust prompts.

Stolen—with attribution—from
[umputun/agterm's `two-agent-chat` recipe](https://github.com/umputun/agterm/tree/master/cookbook/two-agent-chat)
under the MIT license. The published source is in `umputun/agterm`, not `umputun/cc-thingz`.

**Triggers:** "chat with codex", "work with codex", "discuss this with codex", or an incoming
`Chat from Codex:` prompt.

### agterm-backup

Reboot your Mac (for a macOS or [agterm](https://github.com/umputun/agterm) update) **without losing your running Claude Code sessions** — every one comes back **resumed** (`claude --resume <id>`) in its original pane.

agterm already rebuilds the session tree on restart, but it re-runs `claude` *fresh*. This skill closes that gap: a Claude Code hook records each pane's live session id, and after a restart it types `claude --resume <id>` into each restored shell.

Then wire the capture hook (once):

```bash
python3 ~/.claude/skills/agterm-backup/agterm-backup install
```

**Paths:**
- Skill files: `~/.claude/skills/agterm-backup/` — `agterm-backup` (CLI), `capture.py` (the hook), `SKILL.md`.
- Hook: `install` adds `capture.py` to `SessionStart` / `UserPromptSubmit` / `PreToolUse` / `Stop` in `~/.claude/settings.json` (it backs the file up to `settings.json.agterm-backup.bak` first and merges — your existing hooks are preserved).
- State: `~/.agterm-backup/` — `live/<pane>-<role>.json` (per-pane hook captures), `snapshots/` (timestamped backups), `snapshot.json` (latest).

**How it works:**
- Every pane's `AGTERM_SESSION_ID` is stable across a restart (agterm restores the tree keyed by persisted UUIDs), so it's the join key.
- A running claude session's id isn't readable from outside — the hook receives the exact `session_id` on stdin and maps it to the pane. Claude Code re-reads hooks per event, so a freshly-installed hook even captures already-running sessions on their next activity.
- One-shot bonus: `snap --harvest` reads a `Session ID:` line from a pane's `/status` scrollback (validated against a real transcript) to capture sessions that were running before the hook existed.

**Reboot workflow:**

```bash
agterm-backup status            # who's captured
agterm-backup snap --harvest    # freeze the map (before reboot)
# ...reboot / update agterm...
agterm-backup restore --dry-run # review
agterm-backup restore           # type `claude --resume <id>` into each restored pane
```

`restore` skips panes that aren't present or already have claude running, so it's safe to run twice. Preserved flags (e.g. `--dangerously-skip-permissions`) are re-applied on resume.

**Requires:** [agterm](https://github.com/umputun/agterm) (`agtermctl` on PATH) and Claude Code. macOS.

**Triggers:** `agterm-backup`, "reboot without losing sessions", "resume claude after restart", "capture running claude sessions".

Both agents are covered: Codex fires the same hook events with the same payload, so
`install` wires the one capture hook into `~/.claude/settings.json` and
`~/.codex/config.toml`. Codex asks you to trust changed hooks on its next start — pick
"Trust all and continue" once, or the hook never fires.

### memory-review

Turns an agent memory directory into one reviewable document, collects a verdict on every
entry from you, and applies them safely.

Memory rots quietly. A fact is written once, stays true for a month, then keeps being read
for a year — nothing fails, the agent just acts on something that stopped being true. This
walks the whole pile in one sitting: assemble every memory into a single annotatable file
(optionally translated for faster reading), collect your verdicts through
[revdiff](https://github.com/umputun/revdiff), verify the conditional ones against the
actual code before acting, then delete, keep, tag or move — and repair the index and the
wiki-links that deleting just broke.

Snapshots into version control before it deletes anything, and checks that the snapshot
really landed rather than assuming your home directory is versioned.

**Requires:** Claude Code. The review step assumes the `revdiff` skill; any annotation tool
works if you can get line-numbered notes back.

**Triggers:** "memory review", "clean up my memory", "review my memories", "prune memory",
"audit memory", memories look stale or contradict the code.

### revdiff-ru

A wrapper over `/revdiff:revdiff` for people who would rather read the review in Russian.
Translates everything that isn't code — comments, docstrings, markdown prose, commit and PR
text — then opens the normal revdiff TUI on the translated copy.

The hard part is line numbering: the translated copy has to be line-for-line congruent with
the original — same total line count, no wrapping of long Russian sentences — so an annotation on `file:line` still points at the real line in the working tree.
Translation happens in subagents (the raw text never enters the main context) and lands in `/tmp`,
which revdiff opens via `--only`; the working tree is never touched, and fixes go to the originals.

Not `--stdin`: the revdiff launcher starts the TUI in a terminal overlay that doesn't inherit
stdin, so a piped patch dies with `--stdin requires piped or redirected input`.

String literals stay in English on purpose — they're code, and translating them changes behavior.

**Triggers:** `/revdiff-ru`, "review this diff in Russian", "translate the diff and open
revdiff".

### agterm-fork

Forks the agent running in an agterm pane — Claude Code or Codex — into a sibling session:
same workspace, same launch flags, the whole conversation resumed under a fresh session id
(`claude --resume <id> --fork-session`, or `codex fork <id>`). The fork waits at its prompt — you open it and say
what it should do — and the original session carries on untouched.

```bash
agterm-fork                # fork the current pane
agterm-fork install        # add "Fork session" to agterm's command palette (cmd+ctrl+a>f)
```

The plugin puts these commands on `PATH` inside a Claude Code session, so `agterm-fork
install` runs as-is once the plugin is installed.

`install` writes a wrapper to `~/.local/bin` and a managed block in `keymap.conf`, so you
can fork whatever session the cursor is on without going through Claude at all. The wrapper
resolves the newest installed copy of the skill at call time — plugin cache paths carry a
commit sha and would otherwise break on every update.

A resumed claude first asks whether to replay the full session or just a summary; the fork
answers "full session" for you, after waiting out the boot.

Works only inside agterm, and only alongside `agterm-backup`: a session cannot know its own
claude id, so it is read from the live record that skill's hook writes.

**Triggers:** `/bos:agterm-fork`, "fork this session", "continue this in a sibling tab".

### agterm-restart

Restarts every Claude Code running in agterm without losing a conversation: Ctrl+C in each
pane, read the `claude --resume <id>` line claude prints on exit, type the resume back into the
same pane with the original launch flags. For when running sessions must pick up something
they only read at startup — a new binary, `settings.json` env, MCP servers.

```bash
agterm-restart --dry-run   # what would restart
agterm-restart             # restart (skips mid-turn panes; --busy to include them)
agterm-restart install     # add "Restart claude sessions" to the palette (cmd+ctrl+a>c)
```

The palette entry runs in an overlay on the current session and stays open with the report.
A launch prompt in the old argv is not replayed, and the "resume full session or summary"
question is answered "full session".

**Triggers:** `/bos:agterm-restart`, "restart all claude sessions".

### agterm-archive

Parks a whole workspace on disk. Snapshots every session — order, names, cwds, splits with
their ratios, and each pane's agent session id and launch flags — then closes the
workspace. Later, `restore` recreates the whole thing and resumes every agent (Claude Code
or Codex) where it left off.

```bash
agterm-archive archive beware-of-skills   # a whole workspace
agterm-archive session                    # just one session out of it
agterm-archive list
agterm-archive restore beware-of-skills
agterm-archive install    # palette: Archive workspace (cmd+ctrl+a>a), Archive session (cmd+ctrl+a>s),
                          #          Restore archive (cmd+ctrl+a>r)
```

A single session can be parked on its own — it remembers which workspace it came from and
goes back there, recreating the workspace if it is gone. The restore entry lists both kinds
in agterm's native fuzzy picker, so parking and un-parking never needs a Claude session at
all.

For projects that are done for now but not done for good, and shouldn't sit in your sidebar
in the meantime. Complements `agterm-backup` rather than overlapping it: backup covers what
is open across a restart, archive covers what you deliberately closed. Non-claude panes come
back as shells in the right directory — a snapshot is not a checkpoint.

**Triggers:** `/bos:agterm-archive`, "archive this workspace", "bring the workspace back from the archive".

### decomment

Strips the noise comments an AI agent left on a branch: the ones that restate the line below
them, and the ones that narrate the change as a story — "previously this used X", "added
after the incident". Git already holds the history and the code already holds the present.

```bash
/bos:decomment            # everything this branch added
/bos:decomment src/api    # or a narrower scope
```

Scoped to comments the branch itself added, so nobody's older notes get swept up. Comments
the toolchain reads (`eslint-disable`, `@ts-expect-error`, `# noqa`, pragmas) are code in
disguise and stay; so do traps, invariants, and any number someone actually measured. A comment is not atomic either: where an
agent welded one useful sentence to one worthless one, it trims to the survivor instead of
keeping the pair. It proposes the list first — cut, trim, keep, plus what it nearly cut and
kept, which is where you correct its taste.

**Triggers:** `/bos:decomment`, "remove the pointless comments", "the agent commented every
line".

### own-pr

> **Alpha.** The CLI, config format and journal schema may still change without migration.

Every agent flow that opens a pull request ends up inventing its own "what now": draft or
ready, when to review, who to ping. own-pr takes that tail away from all of them. The session
that did the work hands off to it and keeps driving the PR itself, so review feedback never
has to move to another terminal.

The process lives in `~/.config/own-pr/` as Markdown files with frontmatter, like skills.
Edit a file and the next step of every PR in flight follows the new text. `own-pr next`
hands the agent one step at a time with its instructions; `own-pr step` records what
happened.

```
~/.config/own-pr/
  config.md                                 mode: attended | away (machine default)
  repos/github.com/acme/app/
    profiles/feature.md                     which steps, in what order
    steps/pr-open.md                        one file per step
    steps/review.md
    steps/merge.md
  steps/                                    optional: steps shared by every repo
  origins/<flow>.md                         optional: a flow's default profile and notes
```

A step is a few keys and the instruction the agent gets. Keep it short and point at the
skill that does the work: `/skill | $skill` reads for both Claude Code and Codex.

```markdown
---
kind: human
away: auto-pick
---
Run /crit-review | $crit-review.

Attended: once the human has made their picks in its revdiff, record done `--by-human`.
Away: make the picks yourself and record done with `--note` listing what you took and why.
```

`kind` is `auto` (the agent does it) or `human`. `away` says what a human step does while
you are away: `defer` (skip it, owe it to you), `auto-pick` (the agent decides and owes you
the decision) or `wait` (never skipped, e.g. merge). Auto steps take `away: run`.

A profile is a description and an ordered list of steps:

```markdown
---
description: Types only, logic unchanged. Ready PR, no deploy, tests kept.
steps: pr-open, decomment, ci, review, team-handoff, team-feedback, merge
---
```

The session that did the work then goes:

```bash
own-pr start --profile feature   # once per branch
own-pr next                      # NEXT: do pr-open  (kind=auto, mode=attended) + the step text
own-pr bind https://github.com/acme/app/pull/42
own-pr step pr-open done --evidence https://github.com/acme/app/pull/42
own-pr next                      # NEXT: do decomment ...
own-pr step ci running           # before a long wait
own-pr watch --notify --detach  # wait for reviews, comments, merge; a change is typed into this session
```

And you, from any terminal:

```bash
own-pr away             # I'm leaving: defer my steps, keep everything else moving
prs                     # every PR in flight: step, what waits on me, CI, terminal
prs owed                # what waits on me
prs go 42               # jump to the terminal driving that PR
own-pr explain          # this checkout's resolved steps, with the file each came from
```

Every command has `--help` with the details.

When you are away, every step runs except yours: those are deferred or decided by the agent,
and pile up as owed items in `prs owed`. A step marked `away: wait` is never skipped: the
pipeline stops there until you do it. The CLI knows no step by name; what a step means lives
only in its file.

State is one SQLite file in `~/.local/state/own-pr/`. Python 3 stdlib, `gh`, `git`; `prs go`
needs [agterm](https://github.com/umputun/agterm).

**Triggers:** `/bos:own-pr`, "handle the PR", "own-pr", "what PRs are in flight".

## Contributing

Got a skill idea that's equally unhinged? PRs welcome.

## License

MIT
