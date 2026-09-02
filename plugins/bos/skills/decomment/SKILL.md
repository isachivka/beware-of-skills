---
name: decomment
description: >
  Strip the noise comments an AI agent left behind on a branch — the ones that restate the
  code line by line or narrate the change as a story ("was X, now Y", "added a guard here").
  Git holds the history and the code holds the present; only genuinely non-obvious comments
  survive.
when_to_use: >
  Trigger on: decomment, /decomment, "убери бессмысленные комменты", "посмотри на комменты,
  они дублируют код", "почисти комментарии на ветке", "too many comments", "the agent
  commented every line", "drop the narrative comments", cleaning up after an agent that
  documented its own diff.
allowed-tools: [Bash, Read, Edit, Grep, Glob]
argument-hint: 'optional: a ref/path to scope the sweep'
---

# decomment

## Scope

Default: comments **this branch added**, nothing else.

```bash
base=$(git merge-base HEAD origin/HEAD 2>/dev/null || git merge-base HEAD origin/main)
git diff "$base"...HEAD        # committed work on the branch
git diff; git diff --staged    # plus anything still uncommitted
```

Only added (`+`) comment lines are in scope. Pre-existing comments stay unless the user
names them — someone thought about those, and you are not reading their context.
An argument narrows or moves the scope (a ref, a path); honour it and say what you covered.

## Cut

- **Restates the code.** `// increment the counter` over `counter++`; a docstring that
  lists the parameters and their types and says nothing else.
- **Narrates the change.** "previously this used X", "now returns null instead of throwing",
  "moved here from utils", "added after the incident". That is a commit message living in
  the wrong file. `git log -S` finds it forever; the reader of this line does not need it.
- **Announces the obvious.** `// constructor`, `// imports`, `// helper functions`,
  `// early return`, banner bars separating two-line blocks.
- **Explains the language.** What `??`, `useMemo`, a context manager or a try/finally does.
- **Reassures.** "this is safe because we checked above" three lines under the check.

## Trim

A comment is not atomic. The common shape after an agent writes it is one useful sentence
welded to one worthless one:

```
/**
 * A session `uid` is `userId_projectId_sessionHash`.   <- the domain format, unguessable: keep
 * Returns the project id, or `undefined` when the uid  <- the six lines below say this: cut
 * does not have that shape.
 */
```

Cut the dead sentence, keep the live one, and **delete only** — never rewrite the words that
stay, never merge two sentences into a better one. If what survives no longer reads as a
sentence, keep the whole thing and say so in the report.

Two recurring dead openers worth naming:

- **The restated signature.** The first line of a doc block that says what the symbol's own
  name says (`Temp session data is gone` over `classifyMissingSessionData`).
- **Diff voice.** "say *why* here", "note that we now…", "this addresses the review comment".
  A comment talks to whoever opens the file in a year, not to the reviewer of this PR.

## Keep

- **Why, not what** — the reason a non-obvious choice was made, an invariant the types
  cannot express, an ordering that looks arbitrary and is not.
- **A trap.** "looks idempotent, is not", "the API returns 200 on failure", a workaround
  with the upstream issue or ticket it waits on.
- **Anything the toolchain reads**: `eslint-disable`, `@ts-expect-error`, `# type: ignore`,
  `# noqa`, `#pragma`, codegen markers, license headers. These are code wearing a comment's
  clothes — deleting one changes behaviour.
- **Public API docs** in a codebase that documents its public surface, even when they read
  as obvious. Follow the file's neighbours — including their length: a one-line convention
  makes a six-line block on the symbol next door the thing that looks wrong.
- **A measured number.** "batching over 500 doubled p99" earns its line; "for performance"
  does not.
- Anything you are unsure about. The user can always ask for a second, harsher pass.

## How

1. Read the diff, then read each candidate **in its file**, not in the hunk — a comment can
   read as redundant in a diff and carry the file's only warning in place.
2. List what you propose, grouped by file, each with the comment verbatim and one clause of
   reasoning: **cut** whole, **trim** to the surviving sentences (quote what goes and what
   stays), **keep**. Anything you nearly cut and kept goes in a short second list — that is
   where the user corrects your taste.
3. Apply after the user agrees: delete whole comment lines, trailing comments, and — for a
   trim — the dead sentences inside a block. Deletion only: never reword what stays, never
   touch code, never reflow a line you did not cut into. Mind comment-shaped text inside
   strings and regexes.
4. Verify: the repo's typecheck or lint on the touched files, then `git diff` — every hunk
   must be a deletion of comment lines and nothing else.
5. Report the count per file and leave the commit to the user unless they asked otherwise.

Two agents chattering at each other produce the worst of this: each documents its own edit
for the other to read. When the diff is mostly such comments, say so plainly — the fix is a
line in that repo's CLAUDE.md, not a sweep every week.
