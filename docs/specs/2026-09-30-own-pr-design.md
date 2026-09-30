# own-pr: one lifecycle for Igor's own pull requests

Status: alpha. Design agreed 2026-09-30 (Igor, Claude, Codex); implemented on branch feat/own-pr.

## Problem

Several agent flows open pull requests: the jsfiller JS→TS typing waves (wave-pm), the
frontend and backend observability agents (jsf-observability, ws-observability), and Igor's
ad-hoc sessions. Each defines its own "what to do with the PR when done", and they contradict
each other: draft or ready, when crit-review runs, whether the Slack post carries an identity
stamp, who approves Slack posts, the argument order of `/deliver`. None matches how Igor
actually wants a PR handled, and that process changes almost daily.

Igor also loses track of his PRs in flight. Finding which PR is at which stage means walking
through terminal tabs.

## Goals

1. One place defines how Igor's own PRs are handled. Every flow hands off to it and drops its
   own PR tail.
2. The agent that did the work drives the PR in its own session. Feedback never moves to
   another terminal.
3. The process is edited as plain text, per repo, without a plugin release.
4. Human steps can be deferred when Igor is away, so agents keep working, and nothing reaches
   the team before Igor has looked at it.
5. One command shows every PR in flight, what it is doing, what it owes Igor, and which
   terminal owns it.

## Non-goals

- A manager terminal, a daemon, a background executor, or a queue.
- A web dashboard. The overview is CLI only.
- Auto-merge.
- Replacing or editing the existing primitives. `/pr`, `pr-loop`, `crit-review`, `/deliver`,
  `/aqa` and `ask-review` in jsfiller's `.claude/` are used as they are. Mismatches are
  absorbed by the prose of own-pr's steps.
- Finding sessions by title or cwd. Identity comes from the environment or is recorded as
  missing.
- Waking agents that are already idle at a human gate. They wait until Igor types to them.
- Reviewing other people's PRs. That is `request-pr-review` / `~/review`, and stays separate.
- `autonomous-ship` stays for now. It is deleted later, separately.

The engine is neutral: it knows no step, repo, tool or person by name, only `kind`
(`auto|human`), the modes `attended|away` and the step behaviours `run|defer|auto-pick|wait`.
The human acts through `--by-human`; names live in step prose.

## Components

| Part | Lives in | Role |
| --- | --- | --- |
| Skill `own-pr` | `plugins/bos/skills/own-pr/` | How an agent drives a PR: ask for the next step, do it, record the outcome. Shared by Claude Code and Codex. |
| CLI `own-pr` (alias `prs`) | `plugins/bos/bin/` | Resolves the pipeline, keeps the journal, prints the overview. Knows no step by name. Runs no agents. |
| Process config | `~/.config/own-pr/` | Steps, profiles, repo and origin settings. Igor edits it. Versioned by the home dotfiles repo. |
| Journal | `~/.local/state/own-pr/own-pr.db` | SQLite. Written only through the CLI. `own-pr export` dumps JSON. |

The skill is thin: it explains the loop and the recording discipline. What to do at each step
lives in the step files.

## Config

```
~/.config/own-pr/
  config.md                               machine defaults: mode
  steps/<id>.md                           global step library
  repos/<host>/<owner>/<repo>/
    repo.md                               requires, default profile
    steps/<id>.md                         repo steps; same id shadows the global one
    profiles/<name>.md                    description + ordered step ids
  origins/<flow>.md                       root, default profile per target repo, notes
```

All files are Markdown. The CLI parses only a fixed set of `key: value` lines at the top of
each file; values are literal (no inline comments). `kind` is `auto|human`; `away` is `run` for
auto steps and `defer|auto-pick|wait` for human ones; `default` is `auto` or a profile name. Everything else is prose for the agent. Unknown keys are errors.

### Step file

```markdown
kind: human
away: defer

Igor reads the diff, asks questions, criticises. ...
```

- `kind: human` means Igor performs or decides it.
- `away` says what the step does when the effective mode is away:
  - `run` (auto steps): runs as in attended.
  - `defer`: recorded as owed to Igor, the pipeline moves on.
  - `wait`: not skippable; the pipeline stops here in every mode until Igor does it.
  - `auto-pick`: the agent makes the decision Igor would make, logs the choice and the
    reason, and the choice itself becomes an item owed to Igor.
- The step id is its file name. A step does not re-run on its own after new commits; when
  something must be redone after fixes, the step prose that makes the fixes says so.

Step state is deliberately not tied to commit SHAs: that bookkeeping would be a source of
flow bugs, not a guard against code bugs. What changed behind Igor's back is visible through
owed items instead.

### Profile file

```markdown
description: Change with runtime effect in the editor; needs rc09 and autotests.
steps: pr-draft, decomment, strip-tests, eyeball, review, ci, deploy-rc, manual-check, aqa, team-handoff, team-feedback
```

The description states concrete applicability criteria, because an agent may choose a
profile by it. Profiles do not extend or include each other.

Validation, done on every load:
- unknown step id → error
- duplicate step id → error (repeated review rounds are attempts of one step)
- empty or malformed profile → error
- a profile missing any step in `repo.md`'s `requires` → error
- `away` not fitting `kind` → error

Only valid profiles are offered for selection.

### Skipping a step

Dropping steps is what profiles are for. Skipping one step of the chosen profile in one run is
Igor's decision only: he says so in the session, the agent records `skipped` with his reason.
An agent never skips on its own, a step listed in `requires` cannot be skipped, and skipping a
human step does not discharge anything already owed for it.

### repo.md

```markdown
requires: review, ci
default: auto
```

The repo owns its requirements: which steps are mandatory. How it deploys and where review
requests go is written in its own step files.

### origins/<flow>.md

```markdown
root: ~/pdfFiller/ws-observability
profile.github.com/pdffiller/jsfiller: quick

Start every Slack post with 🤖 [WS Observability Agent](https://github.com/pdffiller/ws-observability).
```

An origin is the flow the work came from. It sets a default profile per target repo, and its
prose (notes) is shown by `own-pr next` next to every step, e.g. a stamp the flow puts on its
posts. It cannot drop or replace repo steps.

The origin is resolved once, at `own-pr start`, and stored with the run: `--origin` beats
`OWN_PR_ORIGIN`; otherwise the main worktree root of the directory `own-pr start` runs in
(`git rev-parse --git-common-dir`, so a linked worktree resolves to its repo) is matched
against the `root:` of every origin file; otherwise none. Two origins with the same root is a
config error. An origin without `root:` is only ever chosen explicitly (a flow that shares its
repo with other work, e.g. typing waves in jsfiller). An explicitly named origin that has no file is an error. Later `cd`, worktree
changes or `adopt` never change a stored origin.

## Profile selection

Resolved once when the run starts, then stored:

1. Igor names it in the session, or `--profile`.
2. The origin's profile for this target repo.
3. `repo.md` `default`: a profile name, or `auto`. With `auto` the agent chooses by the
   profile descriptions, records the choice and the reason, and the choice becomes an item
   owed to Igor.

A profile that was named explicitly and does not exist is an error, not a fallback.

Switching profile mid-run is allowed and recorded. The CLI prints the added and removed
steps. Owed items, recorded failures and environment claims survive the switch. Completed
steps carry over by id. An agent
switching to a profile with fewer steps makes that switch an owed item. A running deploy or
AQA finishes and is reconciled before the new step list applies.

## Modes

Two modes: `attended` (default) and `away`. The mode controls how human steps behave. It
never changes the step list or the repo requirements.

Precedence, lowest to highest:
1. `~/.config/own-pr/config.md`, or `own-pr away` / `own-pr attended` (machine flag)
2. `OWN_PR_MODE` in the terminal, read at launch and stored with the run
3. Igor's decision in the session, stored with the run

The mode is resolved again before every step, so switching the machine flag reaches every
run at its next step boundary. `own-pr away` prints which runs stay attended because of a
terminal or run override.

In away mode every step runs, including the team handoff, except human ones: `defer` steps
are deferred as owed items, `auto-pick` steps are decided by the agent (also owed), `wait`
steps stop the pipeline until Igor is back. Back in attended mode, `next` hands him the
deferred steps first. Igor changed this on 2026-09-30: the earlier fixed CLI barrier before
the team handoff is gone.

## Draft until handoff

The PR stays a draft until the `team-handoff` step marks it ready.

For a PR that is already ready when a run adopts it, the run records that state and does not
toggle it back to draft.

## Journal

SQLite, written only through the CLI.

A run holds:
- run id, and once the PR exists: host, repo, PR number and URL
- checkout path and branch
- origin, profile, how each was chosen
- effective mode and where it came from, stored per step decision
- owning session: `CLAUDE_CODE_SESSION_ID` for Claude, the Codex thread id if the
  environment provides it, and `AGTERM_SESSION_ID`; a value the environment does not
  provide is stored as missing
- per step: status (`pending | running | done | failed | deferred | skipped`), attempts,
  evidence links (CI run, crit-review comment, delivery run, AQA
  run, Slack message ts)
- owed items: what and why
- environment claims
- last activity

Plus an append-only event table.

GitHub is the authority for remote facts (PR state, CI, review state). The journal is the
authority for local decisions. `prs` reads PR state from GitHub but never closes a run;
a configured step closes it (`merge` today). Nothing trusts a
recorded "green" from earlier.

`ask-review`'s Slack message ts is stored, so a resumed run updates the original thread and
never posts twice. An uncertain send is reconciled by reading the channel, never retried
blind.

Taking over a run from another session is explicit: `own-pr adopt <run>` records the new
owning session.

## Environment claims

`own-pr env claim rc09` fails while another open run holds rc09. `own-pr env release rc09`
frees it. Closing or merging the run frees it too, but only after any deploy or AQA it
started has finished. Build verification on the desk is `/aqa`'s own job; its TAINTED result
is recorded as `failed`.

## CLI

| Command | Does |
| --- | --- |
| `own-pr start [--profile P] [--origin O]` | Create a run for the current checkout and session |
| `own-pr bind <pr-url>` | Attach the PR to the run |
| `own-pr next` | Print what to do next. A `running` step comes first: reconcile it (finished? result?) before anything else. Then the earliest step that is `failed` or `pending`, given the effective mode. A `failed` step is retried or fixed until it passes or Igor skips it |
| `own-pr step <id> pending\|running\|done\|failed\|skipped [--evidence URL] [--note TEXT]` | Record a step outcome; `pending` re-queues a finished step |
| `own-pr owe <text>` / `own-pr clear <owed-id>` | Record an owed item / record Igor discharging it |
| `own-pr profile <name>` | Switch profile, print the difference |
| `own-pr away` / `own-pr attended` | Machine mode flag |
| `own-pr explain` | The resolved step list and every setting with the file it came from |
| `own-pr env claim\|release <env>` | Environment claims |
| `own-pr adopt <run>` | Take over a run in this session |
| `own-pr export` | Journal as JSON |
| `prs` | Overview of every open run, then Igor's open PRs that no run tracks |
| `prs owed` | Everything waiting on Igor, with the exact question |
| `prs go <pr>` | Select the recorded agterm session; report if it no longer exists |

`prs` columns: PR, repo, title, profile, current execution state (e.g. `aqa running`), owed to
Igor (e.g. `inspection`, `agent's review picks`), CI, last activity, session.

## Today's steps (jsfiller)

| Step | kind | away | What |
| --- | --- | --- | --- |
| `pr-draft` | auto | run | Open the PR as a draft at creation: follow `/pr`'s title and template rules but call `gh pr create --draft` directly, never create-then-convert. `/pr`'s closing question is not asked |
| `decomment` | auto | run | `bos:decomment` on the branch |
| `strip-tests` | auto | run | Only tests the branch added. Coverage padding is removed. Tests that pin a real bug or contract stay, listed with the reason. Existing coverage is never touched |
| `eyeball` | human | defer | Igor reads, asks, criticises |
| `review` | human | auto-pick | `/crit-review`. Attended: Igor picks in revdiff. Away: the agent is the picker, records every accept/decline with a reason, and the picks become owed. Rounds are attempts. After applying fixes, run `bos:decomment` over what the fixes added |
| `ci` | auto | run | `gh pr checks --watch --required`. Failures (tsc, lint, jest, prettier, build) are fixed without asking, one flaky rerun allowed; weakening or skipping tests is not a fix. `pr-loop` is not used: its AQA/ask-review offers and ask-before-fix rule conflict with the pipeline |
| `deploy-rc` | auto | run | `own-pr env claim rc09`, then `/deliver pdfFiller/rc/desk09 <branch>`. Already authorised by own-pr; the agent does not ask again |
| `manual-check` | human | defer | Igor pokes it on rc09 |
| `aqa` | auto | run | `/aqa <pr> rc/desk09` after `deploy-rc`, so `/aqa` never triggers its own delivery. Records the final result, not the launch |
| `team-handoff` | auto | run | Mark ready, then `ask-review` (following origin notes), store the message permalink |
| `team-feedback` | auto | run | Until merged or closed: fix team review comments, decomment what the fixes added, updates go to the original Slack thread |
| `merge` | human | wait | Igor presses merge; the agent records it and closes the run |

Profiles:
- `full`: every step above.
- `quick`: without `deploy-rc`, `manual-check`, `aqa`.

`repo.md`: `requires: review, ci`, `default: auto`.

## Migration

Callers drop their PR tails and end with "hand off to `own-pr`":
- `wave-pm` (global skill and references): its PR, crit-review and ask-review stages.
  wave-pm names `typing-wave` as its profile for jsfiller via `origins/`.
- jsf-observability `investigate` and `observability-pm`: PR, crit-review, ask-review,
  stamp. Stamp moves to `origins/jsf-observability.md`.
- ws-observability `CLAUDE.md` and its `ask-review` wrapper: stamp moves to
  `origins/ws-observability.md`. Dossiers and `docs/progress.md` keep a link to the PR, not
  their own lifecycle state.
- References to `/crit-review2` and to author-side `rvq` are removed.

The jsfiller primitives are not edited.

## Order of work

1. CLI: config loading and validation, `explain`, journal, `start/bind/next/step`, the
   `prs`.
2. Skill `own-pr` and the jsfiller config: steps, `full`, `quick`, `repo.md`.
3. Use it on one real PR in attended mode, then one in away mode. Fix the step prose from
   what goes wrong.
4. Origins and the caller migration, one flow at a time.
5. `env claim`, `adopt`, `prs owed`, `prs go`.

## Open for implementation

- Whether Codex exposes its thread id in the environment. If not, it is stored as missing.
- The `typing-wave` profile's step list, taken from wave-pm when it migrates.
