# beware-of-skills

A collection of Claude Code skills that nobody asked for, but everyone deserves.

## Installation

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill vrednye-sovety
```

## Skills

### vrednye-sovety

Generates poems in the style of [Grigory Oster's "Bad Advice"](https://en.wikipedia.org/wiki/Grigory_Oster) (Вредные советы) based on a situation you describe.

Describe any absurd, funny, or relatable engineering situation — and get back a satirical poem that advises you to do exactly the wrong thing.

**Triggers:** "вредный совет", "остер", "стишок", or any request to turn a situation into a poem.

**Example:**

> *You:* Claude Code created a draft message in Slack and politely asked me to review it before sending. I told it to just send the damn thing.

> *Claude:*
> ```
> Если Claude Code задрафтил
> Сообщение в Slack,
> И спросил тебя учтиво:
> "Может, глянешь, как и что?" —
>
> Ты скажи ему покрепче,
> Не стесняясь в выраженьях,
> Что на драфты тебе плевать,
> Пусть ебашит сразу в чат.
> ```

### flow-recorder

A meta-skill that creates other skills by recording browser workflows. You walk through a routine web process once — clicking buttons, filling forms — and it generates a standalone skill that can replay the process autonomously.

**Install:**

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill flow-recorder
```

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

**Install:**

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill agent-pm
```

**Requires:** the `agterm` skill (all terminal mechanics are delegated to it) and a `claude_yolo` alias (claude with permission checks bypassed).

**Triggers:** "ты менеджер", "ты PM", "оркестрируй агентов", "подними работников", "agent-pm"

**Example:**

> *You:* Ты менеджер по делам document-restoration. Ты ничего не делаешь руками — только даёшь инструкции агентам через agterm и проверяешь их работу.
> *Claude:* *(maps the sessions, asks who is who, and starts running the show)*

### agterm-backup

Reboot your Mac (for a macOS or [agterm](https://github.com/umputun/agterm) update) **without losing your running Claude Code sessions** — every one comes back **resumed** (`claude --resume <id>`) in its original pane.

agterm already rebuilds the session tree on restart, but it re-runs `claude` *fresh*. This skill closes that gap: a Claude Code hook records each pane's live session id, and after a restart it types `claude --resume <id>` into each restored shell.

**Install:**

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill agterm-backup
```

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

### ozon-orders

Gives Claude read access to a self-hosted **Ozon Orders History** service — a personal API over one's [Ozon](https://ozon.ru) purchase history. Ask about past orders, search items by title, check order status (delivered / in progress / cancelled), find returned items, or get spending statistics — and Claude queries the API and answers.

**Install:**

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill ozon-orders
```

**Setup:** the service must be reachable on your network. Default base URL is `http://192.168.1.10:3027`; override with the `OZON_HISTORY_BASE` env var.

**What it exposes** (the whole API): `GET /api/items` (cursor-paginated orders, `q` search, max 200/page), `GET /api/stats` (spending buckets by `year`/`month`/`week` + range totals and returned amount), `GET /api/images/<file>`, `GET /api/health`. A bundled `ozon.py` helper handles pagination and client-side filtering.

```bash
python3 ~/.claude/skills/ozon-orders/ozon.py stats --granularity year
python3 ~/.claude/skills/ozon-orders/ozon.py items --q "нори" --all --count
```

**Triggers:** "ozon orders", "ozon history", "сколько я потратил на озоне", "что заказывали на Озоне", "возвраты", or any question about this person's Ozon purchases.

## Contributing

Got a skill idea that's equally unhinged? PRs welcome.

## License

MIT
