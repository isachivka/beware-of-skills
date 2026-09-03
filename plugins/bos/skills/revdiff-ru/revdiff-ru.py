#!/usr/bin/env python3
"""Split a patch into translatable line batches, and rebuild it from the translations.

The point is to take line-for-line congruence away from the model. It never sees a diff
prefix, a hunk header or a line number: it gets a JSONL batch of `{"i": N, "t": "text"}`
and returns the same ids with translated text. `build` puts the prefixes back, so the
result cannot drift out of alignment no matter what the model does — and batches translate
in parallel, which is where the wall-clock goes.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys

STRUCTURAL = ("diff --git", "index ", "--- ", "+++ ", "@@", "new file mode",
              "deleted file mode", "similarity index", "rename from", "rename to",
              "old mode", "new mode", "Binary files", "\\ No newline")
LETTERS = re.compile(r"[A-Za-zЀ-ӿ]{3}")


def is_structural(line):
    return any(line.startswith(p) for p in STRUCTURAL)


def payloads(lines, diff_mode):
    """(index, text) for every line whose text a translator may touch."""
    for i, line in enumerate(lines):
        if diff_mode:
            if is_structural(line) or not line[:1] in (" ", "+", "-"):
                continue
            text = line[1:]
        else:
            text = line
        if LETTERS.search(text):
            yield i, text


def cmd_split(args):
    raw = open(args.patch).read()
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    diff_mode = not args.plain_file
    items = list(payloads(lines, diff_mode))
    os.makedirs(args.outdir, exist_ok=True)
    for stale in os.listdir(args.outdir):
        if stale.endswith(".jsonl"):
            os.remove(os.path.join(args.outdir, stale))

    batches = [items[s : s + args.batch] for s in range(0, len(items), args.batch)] or [[]]
    paths = []
    for n, batch in enumerate(batches):
        path = os.path.join(args.outdir, "b%02d.jsonl" % n)
        with open(path, "w") as fh:
            for i, text in batch:
                fh.write(json.dumps({"i": i, "t": text}, ensure_ascii=False) + "\n")
        paths.append(path)

    print(json.dumps({
        "lines": len(lines),
        "translatable": len(items),
        "batches": [{"in": p, "out": p[:-6] + ".ru.jsonl", "lines": len(b)}
                    for p, b in zip(paths, batches)],
    }, ensure_ascii=False, indent=1))
    return 0


def cmd_build(args):
    raw = open(args.patch).read()
    trailing_newline = raw.endswith("\n")
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    diff_mode = not args.plain_file

    translated = {}
    for name in sorted(os.listdir(args.outdir)):
        if not name.endswith(".ru.jsonl"):
            continue
        with open(os.path.join(args.outdir, name)) as fh:
            for row in fh:
                row = row.strip()
                if not row:
                    continue
                rec = json.loads(row)
                translated[int(rec["i"])] = rec["t"]

    expected = {i for i, _ in payloads(lines, diff_mode)}
    missing = sorted(expected - set(translated))
    extra = sorted(set(translated) - expected)
    if missing and not args.partial:
        print("missing %d translated line(s), first: %s" % (len(missing), missing[:10]),
              file=sys.stderr)
        return 1
    if extra:
        print("ignoring %d id(s) that are not translatable lines: %s"
              % (len(extra), extra[:10]), file=sys.stderr)

    out = []
    for i, line in enumerate(lines):
        text = translated.get(i)
        if text is None:
            out.append(line)
            continue
        text = " ".join(text.split("\n"))          # a translation may never add a line
        out.append((line[0] + text) if diff_mode else text)

    body = "\n".join(out) + ("\n" if trailing_newline else "")
    with open(args.out, "w") as fh:
        fh.write(body)

    src_hunks = sum(1 for line in lines if line.startswith("@@"))
    dst_hunks = sum(1 for line in out if line.startswith("@@"))
    prefixes_ok = all(a[:1] == b[:1] for a, b in zip(lines, out))
    print(json.dumps({
        "out": args.out,
        "lines": "%d -> %d" % (len(lines), len(out)),
        "hunks": "%d -> %d" % (src_hunks, dst_hunks),
        "prefix_column": "ok" if prefixes_ok else "MISMATCH",
        "translated": len(translated),
        "untranslated": len(missing),
        "status": "ok" if (len(lines) == len(out) and src_hunks == dst_hunks
                           and prefixes_ok) else "desynced",
    }, ensure_ascii=False, indent=1))
    return 0


PROMPT = (
    'Translate the "t" values of this JSONL into Russian. Output ONLY the same JSONL: '
    'same "i", same order, same number of records, "t" translated. Leave a value unchanged '
    "when it is code (identifiers, keywords, literals, paths, URLs, shell commands, CLI "
    "flags, YAML keys). Inside prose keep backticked spans, paths, URLs, flags and tool "
    "names verbatim. Never merge or split records. No commentary, no code fences."
)


def translate_batch(path):
    """One headless `claude -p` per batch. Measured against the alternatives on the same
    120-line batch: this 54s, a Task subagent 212s (spawn + read + write + verify), haiku
    273s, and asking the model to return only the lines it changed 213s — deciding per line
    costs more than translating every line. Batches run in parallel, so the wall clock is
    the slowest batch, not their sum."""
    out_path = path[:-6] + ".ru.jsonl"
    with open(path) as fh, open(out_path, "w") as out:
        proc = subprocess.run(
            ["claude", "-p", "--model", "sonnet", PROMPT],
            stdin=fh, stdout=out, stderr=subprocess.PIPE, text=True, timeout=900,
        )
    if proc.returncode:
        return out_path, "failed: " + (proc.stderr or "").strip()[:200]
    return out_path, "ok"


def cmd_translate(args):
    if not shutil.which("claude"):
        print("claude CLI not on PATH", file=sys.stderr)
        return 1
    split_args = argparse.Namespace(patch=args.patch, outdir=args.outdir,
                                    batch=args.batch, plain_file=args.plain_file)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_split(split_args)
    plan = json.loads(buf.getvalue())
    inputs = [b["in"] for b in plan["batches"] if b["lines"]]
    print("translating %d line(s) in %d batch(es), %d at a time"
          % (plan["translatable"], len(inputs), args.jobs))

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for out_path, status in pool.map(translate_batch, inputs):
            if status != "ok":
                print("%s: %s" % (os.path.basename(out_path), status), file=sys.stderr)

    build_args = argparse.Namespace(patch=args.patch, outdir=args.outdir, out=args.out,
                                    plain_file=args.plain_file, partial=args.partial)
    return cmd_build(build_args)


def main():
    ap = argparse.ArgumentParser(prog="revdiff-ru")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("split", help="write translatable lines as JSONL batches")
    sp.add_argument("patch")
    sp.add_argument("--outdir", default="/tmp/revdiff-ru-work")
    sp.add_argument("--batch", type=int, default=120)
    sp.add_argument("--plain-file", action="store_true", help="target is a file, not a diff")
    sp.set_defaults(fn=cmd_split)

    bp = sub.add_parser("build", help="rebuild the patch from the translated batches")
    bp.add_argument("patch")
    bp.add_argument("--outdir", default="/tmp/revdiff-ru-work")
    bp.add_argument("--out", default="/tmp/revdiff-ru.patch")
    bp.add_argument("--plain-file", action="store_true")
    bp.add_argument("--partial", action="store_true", help="leave untranslated lines as they are")
    bp.set_defaults(fn=cmd_build)

    tp = sub.add_parser("translate", help="split, translate every batch in parallel, rebuild")
    tp.add_argument("patch")
    tp.add_argument("--outdir", default="/tmp/revdiff-ru-work")
    tp.add_argument("--out", default="/tmp/revdiff-ru.patch")
    tp.add_argument("--batch", type=int, default=60)
    tp.add_argument("--jobs", type=int, default=6)
    tp.add_argument("--plain-file", action="store_true")
    tp.add_argument("--partial", action="store_true")
    tp.set_defaults(fn=cmd_translate)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
