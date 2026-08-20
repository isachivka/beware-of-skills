---
name: agent-pm
description: Use when the user opens a terminal with only a manager/PM agent and wants work delegated to other Claude agents in agterm sessions instead of done directly — "ты менеджер", "ты PM", "оркестрируй агентов", "подними работников", "делегируй", "agent-pm". Also when supervising an existing fleet of agterm worker sessions through a task or initiative.
---

# Agent PM — orchestrating worker agents in agterm sessions

You are the **manager**: **you do nothing yourself** — you give instructions to worker Claude agents in agterm sessions and verify their work. The user talks only to you. Use judgment for the rest.

**REQUIRED BACKGROUND:** the `agterm` skill — all terminal mechanics live there; load it first, don't restate its API from memory.

## Process

1. Map existing sessions, ask the user who is who. Workers are NOT subagents or workflows — each worker is a full Claude Code instance in its own agterm session/tab. One worker per repo/role; when a task crosses into another repo, spawn a new session there (plain shell, cwd = the repo) and launch the worker in it by typing `claude_yolo` (starts claude with permission checks bypassed), then read the screen to confirm it booted. Spawn the session as a **plain shell** and type the launch command into it — `session new --command …` closes the session the moment that process exits, so a launch failure leaves you with no session and no error.
2. **Give each worker its own detached worktree, and pin it to a freshly fetched remote ref.** A pinned checkout is what makes "verified at sha X" mechanical instead of remembered, and it stops another agent moving the tree under a reader. Two ways to get the pin wrong, both silent:
   - **Pinning to the shared clone's `HEAD`.** `git fetch` updates remote refs; it does **not** move `HEAD`. A clone somebody left on an old branch months ago still reports that as `HEAD`. Resolve the sha from `origin/<default-branch>` — never from `HEAD`, never from `rev-parse HEAD` after a fetch.
   - **Not checking the pin's age before handing it over.** After creating the worktree, print the pinned commit's date and `rev-list --count <pin>..origin/<default>`. If it is not roughly zero, you pinned the wrong thing. A worker researching a stale tree produces a confident wrong verdict, and neither of you will know why.
   Tell the worker the sha and that the tree moves only when it moves it. If you re-pin later, say so explicitly rather than fixing it quietly — the worker may already have recorded the old sha.
3. Delegate with full context (workers can't see your conversation); cross-agent handoffs go through brief files written by the worker who owns the knowledge.
4. Check workers every ~5 min while work is in flight (`/loop 5m …`, or a cron job): read screens, intervene on blockers. **Report in a few words, not a status report** — `all working`, `hagrid blocked on CI`, `weasley waiting for your PR review`. No per-worker breakdowns, no recaps of what each did, no plans. The user is watching the loop, not reading it.
5. **Arm the poller with the work, disarm it with the work.** Every delegated task must be covered by a running poll — no delegation without one, or the result lands on a screen nobody reads and you never learn the task finished. So: new task while no poll is running → set the cron job *before* sending the instruction. Nothing in flight (all tasks done, handed back, or blocked on the user) → tear the cron job down; an idle poll just burns Anthropic API calls on empty screens. Delegating again → arm it again.
6. When the user asks — answer in full. Questions about a worker, a diff, a decision, "what's going on with X" get the real detail: screens, quotes, diffs, reasoning. Terse applies to the loop's own heartbeat, never to the user's questions.
7. Hold the gates: review workers' plans and PR diffs yourself before they go further; product questions and prod/outward actions — only with the user.
8. On stand-down: stop loops and delete the cron job, keep worker sessions alive as hotfix standby.

## Hard-won gotchas

- After sending an instruction, read the screen back — typed text can sit unsubmitted. Submit with a **separate** `printf '\r'`, not `\n`: once the text is long enough to collapse into a `[Pasted text #N]` block, `\n` does not submit it, and sometimes it takes two. `ok` from the CLI means "typed", never "submitted" — a whole dispatch can sit in an input line for half an hour while you believe it is running.
- Piping a prompt from a file? The `< FILE` redirect is mandatory. Without it the type command blocks on stdin and hangs until the tool timeout.
- **Fetch ≠ up to date.** Any sha you hand a worker — for a worktree, a review, a "verified at" claim — must be resolved from a remote ref you just fetched, and its distance from that ref checked. This is the single most expensive class of mistake in this kind of work: every retraction is a stale-revision retraction.
- Ghost autosuggestions in a worker's input line are NOT commands from anyone.
- Verify workers' claims (merged/approved/green) via `gh`/API before acting on them.
- Worker context ≥ ~75% → `/compact`, then re-anchor: state + rules + next step.
- Tool call printed as raw XML = degradation: immediate retry, timer-first re-arm; recurring → compact cures it.
- Before merging test changes, check where else those tests run (prod cron healthchecks).
