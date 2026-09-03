---
name: revdiff-ru
description: >
  Review a diff in revdiff with everything except the code translated into Russian, line
  numbering preserved 1:1 so annotations map back to the real files. One command does the
  translation; then /revdiff:revdiff opens the result.
when_to_use: >
  Trigger on: revdiff-ru, /revdiff-ru, "ревью на русском", "revdiff по-русски",
  "переведи диф и открой revdiff", "review this diff in Russian".
allowed-tools: [Bash, Skill]
argument-hint: 'optional: ref(s) or file path'
---

# revdiff-ru

1. Build the target as a unified diff: `git diff [ref] > /tmp/revdiff-ru-orig.patch`
   (`gh pr diff N` for a PR).
2. Translate it with the bundled script — one call, nothing else to orchestrate:
   ```bash
   "${CLAUDE_SKILL_DIR}/revdiff-ru.py" translate /tmp/revdiff-ru-orig.patch \
       --out /tmp/revdiff-ru.patch
   ```
   It prints a verification line; `"status": "ok"` means the rebuilt patch has the same line
   count, the same hunk headers and the same prefix column as the original. Anything else,
   stop and show it. A plain file instead of a diff: add `--plain-file`.
3. Run the `revdiff` skill (`/revdiff:revdiff` under Claude Code) on the patch with
   `--stdin` — that is what renders a real diff with hunk navigation. Do NOT use `--only` on
   a translated whole file: it shows current file contents, not the change. The launcher
   runs revdiff in an overlay that does not inherit stdin, so put a shim first on `PATH`:
   `printf '#!/bin/sh\nexec %s "$@" < /tmp/revdiff-ru.patch\n' "$(command -v revdiff)" > /tmp/revdiff-shim/revdiff`
4. Apply annotations to the **original** files — `file:line` matches. Re-review → translate
   again from a fresh diff.

## Why it is a script and not a subagent

The model never sees a diff prefix, a hunk header or a line number: the script hands it
JSONL records of `{"i": N, "t": "text"}` and puts the structure back afterwards, so the
translation cannot drift out of alignment and nothing has to be verified by re-reading.
That removes the slow part. Measured on one 120-line batch:

| how | wall clock |
|---|---|
| `claude -p`, whole batch (what it does now) | 54s |
| Task subagent (spawn, read, write, self-verify) | 212s |
| same but `--effort low` | 55s, and it dropped records |
| haiku instead of sonnet | 273s |
| "return only the lines you translated" | 213s — deciding per line costs more than translating every line |

Batches run in parallel (`--batch 60 --jobs 6`), so a whole patch costs about one batch:
236 lines, 162 of them translatable, came back complete in 55s. Smaller batches do not help
— the floor is process startup plus model latency.
