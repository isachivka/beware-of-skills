---
name: memory-review
description: >
  Use when an agent memory directory has grown large enough that nobody remembers what
  is in it, when memories look stale or contradictory, when the same fact seems to live
  in both memory and a CLAUDE.md, or when the user asks to review, prune, audit or clean
  up their memories. Also use before retiring a project whose memories should move
  somewhere else.
when_to_use: >
  Trigger on: memory review, review my memories, prune memory, clean up memory, audit
  memory, memory got stale, too many memories, "что в моей памяти", "почисти память",
  "разберём память", memories out of date, memory says X but the code says Y.
allowed-tools: Bash, Read, Write, Edit
---

# Reviewing agent memory

Memory rots quietly. A fact is written once, stays true for a month, and then keeps being
read for a year. Nobody notices, because nothing fails — the agent just acts on something
that stopped being true.

This skill turns a memory directory into one reviewable document, gets a verdict on every
entry from the person who owns it, and applies those verdicts safely.

## Overview

Five phases. Do not skip 1 or 4.

1. **Locate and snapshot** — find the real directory, put it under version control first
2. **Assemble** — one document, one heading per file, so verdicts map back
3. **Review** — the owner annotates; you never guess a verdict
4. **Verify** — check the claims you are about to act on
5. **Apply** — delete, keep, tag, move; then repair what deletion broke

## 1. Locate and snapshot

Memory rarely lives where the project dir suggests. Find the real path:

```bash
ls -la ~/.claude/projects/<project-dir>/memory      # often a symlink
readlink ~/.claude/projects/<project-dir>/memory
```

A symlink means several project dirs share one memory — the same files seen N times, not
N copies. Count files at the target, not per project dir.

**Then make deletion reversible before you delete anything.** Confirm with a command, not
an assumption:

```bash
git -C <repo> ls-files <memory-path> | wc -l    # 0 means NOT tracked
```

"My home is a git repo so nothing is lost" is the assumption that bites. A blanket
`*` in `.gitignore`, or a **nested repo** between the memory and the tracking repo, both
produce a silent zero here — `git add -f` will stage nothing and print nothing. If the
count is zero, copy the memory somewhere the tracking repo can actually reach and commit
that, before touching a single file.

## 2. Assemble one document

The owner will not open 77 files. Build one, with a `## <filename>` heading per memory —
those headings are how you map their line-numbered notes back to files.

```bash
for f in "$M"/*.md; do
  echo; echo "## $(basename "$f")"; echo; cat "$f"
done > /tmp/memory-review.md
```

Group by prefix (`user_`, `project_`, `feedback_`, `reference_`) so related entries read
together. Put the index (`MEMORY.md`) first, quoted, as a map.

**Translation:** if the owner reviews faster in another language, translate the assembled
copy — never the memory itself. Memory is read by agents and usually shares the repo's
documentation language. Keep every `## <filename>` heading byte-identical, keep code,
paths, identifiers, branch names, ticket keys and error strings verbatim, and verify with
`diff <(grep '^## ' a) <(grep '^## ' b)` before showing it to anyone. A long translation
belongs in its own session, not the one running the review.

## 3. Review

Open the assembled file for annotation. With the `revdiff` skill:

```
revdiff --only=/tmp/memory-review.md
```

Then map each annotation's line number to the heading above it — a small script beats
counting by hand. Sort verdicts into: **delete**, **keep**, **move elsewhere**, **tag**,
**verify first**.

Expect "move elsewhere" to be common and to be the most valuable output. A fact that every
developer on the repo needs is not memory — it belongs in `CLAUDE.md`, in the repo docs, or
in the skill that performs the action. Collect those into a handoff list rather than acting
on them inside the memory directory.

## 4. Verify before deleting

Some verdicts are conditional: *"this is obsolete — but check, maybe I just never finished
it."* Those are the most valuable annotations in the batch, and the only ones where you can
still be wrong. Check them:

- "already in CLAUDE.md" → grep it; if true, delete rather than move
- "this work is done" → grep the code for the thing it claims shipped
- "this no longer applies" → run the command the memory describes

Report what you found even when it confirms the verdict. The owner asked because they were
not sure.

## 5. Apply, then repair

Deleting memories breaks things inside the memories that survive:

- **Index** — prune `MEMORY.md` of entries whose file is gone, and verify zero broken links
- **Wiki-links** — `[[some-name]]` resolves against the `name:` frontmatter field, **not**
  the filename. Resolve against `name:` or you will report live links as dead and miss real
  ones. Then remove links whose target you just deleted.
- **Cross-references in prose** — a trailing `Related: [[a]], [[b]]` line can be dropped
  whole; a mid-sentence reference needs the sentence rewritten.

**Tagging instead of deleting.** Memories scoped to a finite effort (a migration, a
refactor, a launch) should not be re-read one by one when it ends. Add a scope marker to
their frontmatter so they can be found and dropped as a set:

```yaml
metadata:
  scope: ts-migration-pdf-9268
```

## Standing rules worth enforcing during review

- **No "it was X, now it is Y" memories.** They read as current state and mislead the next
  agent. Record what is true now, or nothing.
- **No evidence-collection memories.** "Verified on 2026-08-14 that…" is a receipt, not a
  fact worth carrying.
- **A memory that is really a process belongs in a skill.** If an entry reads like
  instructions for performing a task, it is skill material.
- **Situational memories die.** A note about one incident, one flaky run, one broken tag is
  not a durable fact.

## Hard-won gotchas

- `git add -f` staging nothing, with no error, means a **nested repo** sits between the
  path and the tracking repo. Check with `git rev-parse --show-toplevel` at the target.
- **zsh does not word-split an unquoted variable** the way bash does. A `for f in $LIST`
  loop over a space-separated string silently iterates once, over the whole string, and
  reports zero matches. Run batch deletions under `bash -c`.
- A **TUI review can outlive the process that launched it.** If the launcher times out, the
  annotations are not lost — they are written to disk on quit and flushable mid-session.
  Read the output file rather than relaunching, which would discard them.
- Counting memory files through several project dirs **multiplies a symlink**. 77 files seen
  from 8 project dirs is 77 files, not 616.
- When a memory names a path that no longer exists (a retired clone, a moved directory),
  the fact inside it may still be true elsewhere. Re-check it in the current setup before
  deciding — the fix is often a rewrite, not a deletion.
