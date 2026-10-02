---
name: own-pr
description: Drive one of the user's own pull requests from "the work is done" to its end, in the session that did the work, following the process the user keeps as steps and profiles in ~/.config/own-pr. Use when a flow hands off to own-pr, when the user says the work is ready for a PR ("own-pr", "handle the PR", "доведи PR", "оформи PR", "дальше по PR"), when resuming a PR this session owns, or when they ask what PRs are in flight ("prs", "что у меня в работе"). Not for reviewing other people's PRs.
---

# own-pr

> Alpha: the CLI and config format may still change. If a command's usage differs from this
> file, `own-pr --help` and `own-pr <command> --help` are the truth.

You drive this PR through the user's current process. The process is not written here: it
lives in `~/.config/own-pr/` (or `$OWN_PR_CONFIG_DIR`) and changes often. `own-pr next` hands
you one step at a time together with that step's instructions. Follow them.

## The loop

1. **Start once per branch**, in the checkout: `own-pr start`.
   - If the calling flow named an origin or profile, pass `--origin NAME` / `--profile NAME`.
   - If the user named a profile, pass `--profile NAME`.
   - If it answers with a list of profiles, pick by the descriptions and run
     `own-pr start --profile NAME --auto-reason "<why, one line>"`. Your pick is owed to the user.
2. **Ask for the next step**: `own-pr next`. It prints `NEXT: <action> <step> (...)`, the PR
   link, notes from the origin flow if any, and the step's instructions.
3. **Before anything long** (a wait on CI, a deploy, a test run, a review):
   `own-pr step <id> running`.
4. **Do the step**, then record what actually happened:
   `own-pr step <id> done|failed [--evidence URL] [--note TEXT]`.
5. **Repeat** from 2 until `NEXT: done`, or until a step says to wait for the user.

Once the PR exists: `own-pr bind <pr-url>`.

## What the actions mean

| Action | Do |
| --- | --- |
| `do` | Run the step. |
| `retry` | It failed before: fix the cause, run it again. |
| `reconcile` | It is marked running (a long wait, or the session stopped mid-step): find out where it stands and record `done` or `failed` once it has ended. Start no other work of your own before that. |
| `done` | Every step of the profile is finished. |

A profile with `repeat: true` never ends: when an item is finished, `next` closes it, opens
the next one (`ITERATION n started`) and hands you its first step. Just keep going; the new item
has no PR until you `bind` one.

## The user's steps

`own-pr start` and every `own-pr next` print a `PLAN` line: the whole profile, `▶` where you
are, `✓` done, `[you]` the user's steps, each listed below it with a one-line summary. When the user says they already did something ("я
посмотрел", "смёржил", "проверил на rc") — even a step that is still ahead — find it among the
`[you]` steps in PLAN and record `own-pr step <id> done --by-human` right away. Exactly one
`[you]` step fits: do it without asking. Several or none fit: ask, listing the `[you]` step ids.
The user can also record it themselves with `prs done <pr> <step>`.

- `the human's step — ask them and wait`: tell the user what is needed and stop until they
  answer. Record `--by-human` only for what they actually did or said.
- `agent decides` (away mode): make the decision the user would make, and record `done` with
  `--note` listing what you chose and why. It becomes owed to the user automatically.
- Deferred steps are handled by `own-pr next` itself. You never record `deferred`.

## Things only the user decides

Record these only when the user said them in this session:
- Skip a step: `own-pr step <id> skipped --by-human --note "<their reason>"`.
- "I'm away" / "I'm back" for this PR: `own-pr mode away|attended` (`clear` drops the override).
- They have looked at something owed: `own-pr clear <id> --by-human` (ids in `prs owed`).
  Fixing what an owed item describes does not clear it; only the user looking does.
- Another profile: `own-pr profile NAME --by-human`. Switching on your own (no `--by-human`)
  is allowed, but dropping steps that way is owed to the user.

## Other commands

| Command | For |
| --- | --- |
| `own-pr explain` | The resolved step list and every setting with the file it came from |
| `own-pr step <id> pending` | A finished step must run again; `next` sends you back to it |
| `own-pr owe "<text>" [--step ID]` | Something the user should look at (shown in `prs owed`) |
| `own-pr env claim\|release <name>` | Hold a shared resource that other PRs must not use meanwhile |
| `own-pr watch --notify --detach` | Wait for the PR to change, for as long as it takes: returns at once, a background watcher types a line into this session on a change |
| `own-pr adopt <run>` | This session takes over a run another session started |
| `own-pr close` | End the run |
| `prs`, `prs owed`, `prs go <pr>` | Every PR in flight, what waits on the user, jump to the owning terminal |
| `prs log [<pr>]` | Closed items, newest first; with a PR or run id, that item's steps |
| `prs done\|skip <pr> <step>`, `prs away\|attended <pr>` | The user records their step or switches one PR's mode from their own terminal; a session waiting on it gets a nudge |

## Rules

- Never record `done` for something you did not verify.
- A refused command (`own-pr: ...`) is an answer, not a glitch: read it and act on it.
