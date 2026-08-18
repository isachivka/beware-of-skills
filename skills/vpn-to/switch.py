#!/usr/bin/env python3
"""Flip the PBR mark on xray's outbound in the local router repo.

Edits ONLY <repo>/configs/04_outbounds.json on this machine. Never touches the
router — deployment is a separate step (commit, push, pull, run.sh).

Usage:
  switch.py --show                 print the currently active mark
  switch.py <mark>                 make <mark> the active one, comment the rest
  switch.py <mark> --repo <path>   non-default repo location

Exit codes: 0 ok / 1 error / 2 already on the requested mark (no write)
"""

import argparse
import json
import os
import re
import sys

MARK_RE = re.compile(r'^(?P<indent>\s*)(?P<off>//\s*)?"mark":\s*(?P<val>\d+)\s*,?\s*$')


def strip_comments(s):
    """Same comment handling xray's config loader does: // and /* */ outside strings."""
    out, i, n, instr, esc = [], 0, len(s), False, False
    while i < n:
        c = s[i]
        if instr:
            out.append(c)
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                instr = False
            i += 1
            continue
        if c == '"':
            instr = True
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n and s[i + 1] == '/':
            while i < n and s[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and s[i + 1] == '*':
            i += 2
            while i + 1 < n and not (s[i] == '*' and s[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def find_mark_lines(lines):
    hits = []
    for idx, line in enumerate(lines):
        m = MARK_RE.match(line)
        if m:
            hits.append((idx, m))
    return hits


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('mark', nargs='?', help='decimal PBR mark to activate')
    ap.add_argument('--show', action='store_true')
    ap.add_argument('--repo', default=os.path.expanduser('~/pets/router'))
    args = ap.parse_args()

    path = os.path.join(args.repo, 'configs', '04_outbounds.json')
    if not os.path.isfile(path):
        sys.exit(f'not found: {path}')

    raw = open(path, encoding='utf-8').read()
    lines = raw.split('\n')
    hits = find_mark_lines(lines)
    if not hits:
        sys.exit(f'no "mark" line found in {path} — add a sockopt block first')

    active = [(i, m) for i, m in hits if not m.group('off')]
    if len(active) > 1:
        sys.exit('more than one active "mark" line — fix the file by hand')
    current = active[0][1].group('val') if active else None

    if args.show or args.mark is None:
        print(current if current is not None else '0 (no active mark — table main)')
        return

    want = args.mark
    if current == want:
        print(f'already {want}, nothing to write')
        sys.exit(2)

    known = [m.group('val') for _, m in hits]
    if want not in known:
        # keep the requested one first so it stays visible at the top of the block
        known.insert(0, want)

    indent = hits[0][1].group('indent')
    block = [
        f'{indent}"mark": {v}' if v == want else f'{indent}// "mark": {v}'
        for v in dict.fromkeys(known)
    ]

    first, last = hits[0][0], hits[-1][0]
    lines[first:last + 1] = block
    new = '\n'.join(lines)

    try:
        cfg = json.loads(strip_comments(new))
    except Exception as e:
        sys.exit(f'result would not parse as xray config: {e}')

    got = cfg['outbounds'][0].get('streamSettings', {}).get('sockopt', {}).get('mark')
    if str(got) != want:
        sys.exit(f'sanity check failed: parsed mark is {got!r}, expected {want}')

    open(path, 'w', encoding='utf-8').write(new)
    print(f'{current} -> {want}')


if __name__ == '__main__':
    main()
