---
name: own-pr
description: Drive one of Igor's own pull requests from "the work is done" to merged, in the session that did the work — draft PR, comment and test cleanup, Igor's review, crit-review/revmux, CI, rc deploy, autotests, team review — following the steps and profiles in ~/.config/own-pr. Use when a flow hands off to own-pr, when Igor says the work is ready for a PR ("own-pr", "handle the PR", "доведи PR", "оформи PR", "дальше по PR"), when resuming a PR this session owns, or when he asks what PRs are in flight ("prs", "что у меня в работе"). Not for reviewing other people's PRs — that is request-pr-review.
---

# own-pr

You drive this PR through Igor's current process. The process is not written here: it lives
in `~/.config/own-pr/` and changes often. `own-pr next` hands you one step at a time together
with that step's instructions. Follow them.

## The loop

1. **Start once per branch**, in the checkout: `own-pr start`.
   - If the calling flow named an origin or profile, pass `--origin NAME` / `--profile NAME`.
   - If Igor named a profile, pass `--profile NAME`.
   - If it answers with a list of profiles (`default: auto`), pick by the descriptions and run
     `own-pr start --profile NAME --auto-reason "<why, one line>"`. Your pick is owed to Igor.
2. **Ask for the next step**: `own-pr next`. It prints `NEXT: <action> <step> (...)`, the PR
   link, the Slack stamp if any, and the step's instructions.
3. **Before anything long** (CI wait, delivery, autotests, team review):
   `own-pr step <id> running`.
4. **Do the step**, then record what actually happened:
   `own-pr step <id> done|failed [--evidence URL] [--note TEXT]`.
5. **Repeat** from 2 until `NEXT: done` or `NEXT: blocked`.

Once the PR exists: `own-pr bind <pr-url>`.

## What the actions mean

| Action | Do |
| --- | --- |
| `do` | Run the step. |
| `retry` | It failed before: fix the cause, run it again. |
| `reconcile` | It was running when the session stopped: find out what really happened (run finished? result?) and record `done` or `failed` before anything else. |
| `blocked` | The team-handoff barrier. Stop and tell Igor what is waiting on him. Never work around it. |
| `done` | Every step of the profile is finished. |

## Igor's steps (`kind=human`)

- Attended: Igor does them. Ask, wait for him. Record `--by-igor` only for what he actually did
  or said.
- Away, `agent decides`: you make the decision he would make, and record `done` with `--note`
  listing every accept/decline and why. It becomes owed to him automatically.
- Away, deferred steps are handled by `own-pr next` itself. You do not record `deferred`.

## Things only Igor decides

Record these only when Igor said them in this session:
- Skip a step: `own-pr step <id> skipped --by-igor --note "<his reason>"`.
- "Waive my review": `own-pr waive --by-igor`.
- "I'm away" / "I'm back" for this PR: `own-pr mode away|attended` (`clear` drops the override).
- He has looked at something owed: `own-pr clear <id> --by-igor` (ids in `prs owed`). Fixing
  what an owed item describes does not clear it; only Igor looking does.
- Another profile: `own-pr profile NAME --by-igor`. Switching on your own (no `--by-igor`) is
  allowed, but dropping steps that way is owed to him.

## Other commands

| Command | For |
| --- | --- |
| `own-pr explain` | The resolved step list and every setting with the file it came from |
| `own-pr handoff-check` | What still blocks the team handoff |
| `own-pr owe "<text>" [--step ID]` | Something Igor must look at before handoff |
| `own-pr env claim\|release rc09` | Hold a shared desk while deploy, manual check and autotests use it |
| `own-pr adopt <run>` | This session takes over a run another session started |
| `own-pr close` | PR merged or closed |
| `prs`, `prs owed`, `prs go <pr>` | Overview of every PR in flight, what waits on Igor, jump to the owning terminal |

## Rules

- Never record `done` for something you did not verify.
- A refused command (`own-pr: ...`) is an answer, not a glitch: read it and act on it.
- PR titles and bodies, commits, review replies and Slack posts are in English.
- Never merge the PR.
