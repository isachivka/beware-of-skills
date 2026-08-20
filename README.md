# beware-of-skills

A collection of Claude Code skills that nobody asked for, but everyone deserves.

## Installation

This repo is a Claude Code plugin marketplace with two plugins: **bos** (the general set) and
**bosp** (skills wired to my own hardware and accounts — you almost certainly want to skip it).

```
/plugin marketplace add isachivka/beware-of-skills
/plugin install bos@beware-of-skills
```

Skills then invoke as `/bos:<skill>`, e.g. `/bos:agent-pm`. `/plugin update` keeps them current.

## Skills — `bos`

### flow-recorder

A meta-skill that creates other skills by recording browser workflows. You walk through a routine web process once — clicking buttons, filling forms — and it generates a standalone skill that can replay the process autonomously.

**Features:**
- Three auth modes: **manual** (you log in yourself), **credentials** (hardcoded for convenience), **none**
- Stable element identification — relies on visible text, `data-testid`, and HTML ids instead of fragile CSS classes
- **Update mode** — walk through an existing flow to patch steps when the site UI changes
- Automatically asks whether field values should be hardcoded or prompted at runtime

**Triggers:** `record flow`, `automate website`, `create browser skill`

**Example:**

> *You:* record flow
> *Claude:* What's the flow name, URL, auth type, and a short description?
> *You:* `submit-meters`, `https://utility.example.com`, credentials, submit monthly meter readings
> *Claude:* *(opens browser, logs in, then follows your instructions step by step, recording everything)*
> *You:* done
> *Claude:* *(generates `~/.claude/skills/submit-meters/SKILL.md`)*

### agent-pm

Turns Claude into a **manager that does nothing itself** — it orchestrates a fleet of full Claude Code instances running in [agterm](https://github.com/umputun/agterm) sessions: one worker per repo/role, delegation with briefs, a 5-minute check loop, PM-held gates (plan/PR review, prod actions), and battle-tested recovery playbooks for degraded workers.

Born from a real production day: a frontend redesign shipped through 3 feedback iterations, a public buglash, a cross-repo fix, and an A/B experiment launch — all driven by one PM agent supervising 4 worker agents.

**Requires:** the `agterm` skill (all terminal mechanics are delegated to it) and a `claude_yolo` alias (claude with permission checks bypassed).

**Triggers:** "ты менеджер", "ты PM", "оркестрируй агентов", "подними работников", "agent-pm"

**Example:**

> *You:* Ты менеджер по делам document-restoration. Ты ничего не делаешь руками — только даёшь инструкции агентам через agterm и проверяешь их работу.
> *Claude:* *(maps the sessions, asks who is who, and starts running the show)*

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

**Triggers:** "memory review", "почисти память", "review my memories", "prune memory",
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

**Triggers:** `/revdiff-ru`, "ревью на русском", "revdiff по-русски", "переведи диф и открой
revdiff".

### agterm-fork

Forks the claude running in an agterm pane into a sibling session: same workspace, same
launch flags, the whole conversation resumed under a fresh session id
(`claude --resume <id> --fork-session`). The fork waits at its prompt — you open it and say
what it should do — and the original session carries on untouched.

```bash
agterm-fork                # fork the current pane
agterm-fork install        # add "Fork session" to agterm's command palette (ctrl+a>f)
```

`install` writes a wrapper to `~/.local/bin` and a managed block in `keymap.conf`, so you
can fork whatever session the cursor is on without going through Claude at all. The wrapper
resolves the newest installed copy of the skill at call time — plugin cache paths carry a
commit sha and would otherwise break on every update.

Works only inside agterm, and only alongside `agterm-backup`: a session cannot know its own
claude id, so it is read from the live record that skill's hook writes.

**Triggers:** `/bos:agterm-fork`, "форкни сессию", "fork this session".

### agterm-archive

Parks a whole workspace on disk. Snapshots every session — order, names, cwds, splits with
their ratios, and each pane's claude session id and launch flags — then closes the
workspace. Later, `restore` recreates the whole thing and resumes every claude where it left
off.

```bash
agterm-archive archive beware-of-skills
agterm-archive list
agterm-archive restore beware-of-skills
agterm-archive install       # palette: "Archive workspace" (ctrl+a>a), "Restore workspace" (ctrl+a>r)
```

The restore entry lists your archives in agterm's native fuzzy picker, so parking and
un-parking a project never needs a Claude session at all.

For projects that are done for now but not done for good, and shouldn't sit in your sidebar
in the meantime. Complements `agterm-backup` rather than overlapping it: backup covers what
is open across a restart, archive covers what you deliberately closed. Non-claude panes come
back as shells in the right directory — a snapshot is not a checkpoint.

**Triggers:** `/bos:agterm-archive`, "заархивируй воркспейс", "верни воркспейс из архива".

## Skills — `bosp` (personal)

Wired to my home router and my Ozon account. Install with `/plugin install bosp@beware-of-skills` if you really want them.

### ozon-orders

Gives Claude read access to a self-hosted **Ozon Orders History** service — a personal API over one's [Ozon](https://ozon.ru) purchase history. Ask about past orders, search items by title, check order status (delivered / in progress / cancelled), find returned items, or get spending statistics — and Claude queries the API and answers.

**Setup:** the service must be reachable on your network. Default base URL is `http://192.168.1.10:3027`; override with the `OZON_HISTORY_BASE` env var.

**What it exposes** (the whole API): `GET /api/items` (cursor-paginated orders, `q` search, max 200/page), `GET /api/stats` (spending buckets by `year`/`month`/`week` + range totals and returned amount), `GET /api/images/<file>`, `GET /api/health`. A bundled `ozon.py` helper handles pagination and client-side filtering.

```bash
python3 ~/.claude/skills/ozon-orders/ozon.py stats --granularity year
python3 ~/.claude/skills/ozon-orders/ozon.py items --q "нори" --all --count
```

**Triggers:** "ozon orders", "ozon history", "сколько я потратил на озоне", "что заказывали на Озоне", "возвраты", or any question about this person's Ozon purchases.

### vpn-to

Switches which uplink the home router's xkeen/xray tunnel dials the VPS over, and reports
which one it is on now. `/vpn-to nw`, `/vpn-to rt`, or no argument for status.

Very specific to one Keenetic router with two ISPs, but the mechanism generalises: on
KeeneticOS the provider checkboxes in a connection policy decide which *clients* get
redirected into xkeen — they do nothing for xray's own outbound socket. xkeen deliberately
excludes xray from its OUTPUT chain by gid, so without a mark the tunnel leaves over the
default route no matter what the web interface says. The uplink is chosen by
`streamSettings.sockopt.mark`, which lands in an `ip rule` and picks the policy's routing
table.

Reads the policy codes off the router instead of hardcoding them, keeps the edit strictly
one-directional (local repo → commit → push → pull → `run.sh`, never an edit on the router,
which the deploy script would clobber anyway), validates the JSON survives xray's comment
stripping before writing, and refuses to restart the tunnel when nothing changed.

**Triggers:** `/vpn-to rt`, `/vpn-to nw`, "переключи впн на ростелеком", "через какой
провайдер сейчас впн", VPN slow because one provider's route degraded.

## Contributing

Got a skill idea that's equally unhinged? PRs welcome.

## License

MIT
