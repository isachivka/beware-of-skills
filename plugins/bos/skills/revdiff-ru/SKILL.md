---
name: revdiff-ru
description: >
  Review a diff in revdiff with everything except the code translated into Russian,
  line numbering preserved 1:1 so annotations map back to the real files. Thin wrapper:
  translate the patch in a subagent, then run /revdiff:revdiff.
when_to_use: >
  Trigger on: revdiff-ru, /revdiff-ru, "ревью на русском", "revdiff по-русски",
  "переведи диф и открой revdiff", "review this diff in Russian".
allowed-tools: [Agent, Bash, Skill]
argument-hint: 'optional: ref(s) or file path'
---

# revdiff-ru

1. Build the target as a unified diff: `git diff [ref] > /tmp/revdiff-ru-orig.patch`
   (`gh pr diff N` for a PR). A plain file target instead → copy it to `/tmp/revdiff-ru/`.
2. One `general-purpose` subagent, `model: sonnet` (translation is mechanical), writes the
   translated patch to `/tmp/revdiff-ru.patch`. The main thread never reads file contents.
   Subagent returns only `path / lines / hunks / status`.
   - Translate: prose, comments, docstrings, markdown, commit/PR text.
   - Verbatim: code, string literals, paths, URLs, commands, flags, backticked/fenced content,
     and all diff plumbing — `@@` headers, `---`/`+++`, the leading ` `/`+`/`-` of every line.
   - Line N out = line N in. Same line count, no wrapping, no merging, no splitting.
3. Verify: equal `wc -l`, equal `grep -c '^@@'`, and `diff` of the leading-character column
   (`sed 's/^\(.\).*/\1/'`) silent. Mismatch → re-dispatch, never fix by hand.
4. Run `/revdiff:revdiff` on the patch with `--stdin` — that is what renders a real diff with
   hunk navigation. Do NOT use `--only` on translated whole files: it shows current file
   contents, not the change. The launcher runs revdiff in an overlay that does not inherit
   stdin, so put a shim first on `PATH`, then launch:
   `printf '#!/bin/sh\nexec %s "$@" < /tmp/revdiff-ru.patch\n' "$(command -v revdiff)" > /tmp/revdiff-shim/revdiff`
5. Apply annotations to the **original** files — `file:line` matches. Re-review → re-translate fresh.
