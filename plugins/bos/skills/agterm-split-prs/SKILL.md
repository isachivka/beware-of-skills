---
name: agterm-split-prs
description: >
  Hand the pull requests this session has been juggling off to agterm sessions of their own:
  one sibling session per PR, each in a worktree on the PR's branch, each running a fresh
  agent with a brief written from this conversation. Optionally starts a flows process
  (ext-pr, jsf-pr, …) in each. This session lets go of those PRs afterwards.
when_to_use: >
  Trigger on: agterm-split-prs, /agterm-split-prs, "split the PRs into sessions", "a session per
  PR", "create separate sessions for both PRs", "раздай PR по сессиям", "отбери PR в отдельные
  сессии", "по сессии на каждый PR", or when one conversation holds several PRs and the user wants
  to run a per-session flow (`flow start … --bind`) on each.
allowed-tools: [Bash, Read, Write]
argument-hint: 'optional: which PRs; optional: --flow <process>'
---

# agterm-split-prs

Works only inside agterm (`AGTERM_ENABLED=1`). Every `agtermctl` call below takes
`--socket "$AGTERM_SOCKET"` after the subcommand, as its own argument.

## 1. The PRs

List every PR this conversation worked on: repo, number, URL, head branch, state
(`gh pr view <url> --json number,url,headRefName,state,isDraft`). Merged or closed ones stay out.
The user named some: only those. Unclear which: ask, listing them. Show the list in one line each
before going on.

## 2. A checkout per PR

Never switch the main checkout: it may be dirty or on someone else's branch.

- A worktree already on that branch (`git worktree list`): reuse it.
- Otherwise add one where the repo keeps them: `.worktrees/<slug>` if `git check-ignore -q
  .worktrees/x` says it is ignored, else a sibling `../<repo>-wt-<slug>`. Then check the PR out
  there, which also sets the upstream and handles PRs from forks:

  ```bash
  git -C <main> worktree add --detach <path> && cd <path> && gh pr checkout <n>
  ```

## 3. A brief per PR

Write `<scratchpad>/briefs/<repo>-<n>.md`, in English, self-contained: the new agent has none of
this conversation. It holds:

- the PR (URL, branch → base) and that the directory is a worktree of it;
- what the PR does, in a few lines, and its state (draft, CI, reviews);
- what this conversation decided about it, and what is still open for the user;
- shared background the PRs have in common (one paragraph, the same in every brief);
- the rules that applied here: what needs the user's explicit go (marking ready, reviewers,
  Slack, merge, anything irreversible), commit conventions, the language to talk to the user in;
- the first move: read the PR (`gh pr view <n> --comments`, `gh pr diff <n>`), give the user a
  short status, wait for instructions.

No single quotes in the brief's path: it is read inside a `zsh -lc '…'`.

## 4. The sessions

Launch the agent the way this one was launched: read this pane's `foreground` from
`agtermctl tree --json` for the session `$AGTERM_SESSION_ID` and keep its flags
(`--dangerously-skip-permissions`, `--model …`), dropping any prompt or `--resume`.

```bash
prev="$AGTERM_SESSION_ID"
id=$(agtermctl session new --socket "$AGTERM_SOCKET" --after "$prev" --no-select \
  --cwd <worktree> --name "<repo>#<n>" \
  --command "zsh -lc 'claude <flags> \"\$(cat <brief>)\"'")
agtermctl session context "<repo>#<n> <what it is>" --target "$id" --socket "$AGTERM_SOCKET"
prev="$id"   # the next one goes after this one, keeping the PRs in order
```

- `--after` already names the workspace: never pass `--workspace` with it.
- `session context` takes the text first, then the options.

## 5. Check they came up

About 20 seconds later, for each id: `tree --json` shows `claude` in its `foreground`, and
`agtermctl session text --target <id> --lines 15` shows it working. A new folder makes Claude ask
"Do you trust this folder?": do not answer it for the user, tell them which session waits on it.

## 6. A flow in each (only if asked)

`--flow <process>` given, or the user asked to run a flow per PR: once a session's agent is at
its prompt, `flow start <process> --bind dev=<id>` for it. flowd types the step into that
session; its agent reports there, not here.

## 7. Let go

Report a table: session name, worktree, state (working / waits on trust / flow run id). From now
on these PRs belong to their sessions: do not commit, push or comment on them from here. A
question about one: point the user to its session.
