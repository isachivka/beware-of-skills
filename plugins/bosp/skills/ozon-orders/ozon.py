#!/usr/bin/env python3
"""Tiny CLI over the "Ozon Orders History" API.

Handles cursor pagination and client-side filtering so an agent can answer
questions about Ozon purchases, returns, and spending without re-implementing
the paging loop each time. Stdlib only.

Base URL: $OZON_HISTORY_BASE or http://192.168.1.10:3027
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("OZON_HISTORY_BASE", "http://192.168.1.10:3027").rstrip("/")
MAX_LIMIT = 200  # server returns an empty page above this


def _get(path, params=None):
    url = f"{BASE}/api{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code} for {url}: {body}")
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach {url}: {e.reason}")


def iter_items(q=None, page_limit=MAX_LIMIT):
    """Yield every item, walking cursors from newest to oldest."""
    cursor = None
    seen = set()
    while True:
        data = _get("/items", {"q": q, "limit": page_limit, "cursor": cursor})
        items = data.get("items", [])
        if not items:
            break
        for it in items:
            if it["id"] in seen:  # guard against a non-advancing cursor
                return
            seen.add(it["id"])
            yield it
        cursor = data.get("nextCursor")
        if cursor is None:
            break


def cmd_health(_):
    print(json.dumps(_get("/health"), ensure_ascii=False))


def cmd_items(a):
    if a.all:
        rows = list(iter_items(q=a.q))
    else:
        rows = _get("/items", {"q": a.q, "limit": min(a.limit, MAX_LIMIT), "cursor": a.cursor}).get("items", [])
    if a.status:
        rows = [r for r in rows if r.get("status") == a.status]
    if a.returned:
        rows = [r for r in rows if r.get("returned")]
    if a.count:
        print(len(rows))
        return
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for r in rows:
        ret = " [RETURNED]" if r.get("returned") else ""
        print(f'{r["orderDate"]}  {r["price"]:>7} ₽  {r["status"]:<12}  '
              f'{r["orderId"]}  {r["title"]}{ret}')
    if not a.count:
        print(f"\n{len(rows)} item(s)", file=sys.stderr)


def cmd_stats(a):
    data = _get("/stats", {"granularity": a.granularity, "from": getattr(a, "from"), "to": a.to})
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for b in data.get("buckets", []):
        print(f'{b["period"]:<8} {b["spent"]:>10} ₽')
    print(f'\nTotal spent:    {data.get("totalSpent"):>10} ₽')
    print(f'Total returned: {data.get("totalReturned"):>10} ₽  ({data.get("currency")})')


def cmd_image(a):
    fname = a.file if a.file.startswith("/api/") else f"/images/{a.file}"
    url = f"{BASE}/api{fname}" if not fname.startswith("/api") else f"{BASE}{fname}"
    out = a.out or os.path.basename(fname)
    urllib.request.urlretrieve(url, out)
    print(out)


def main():
    p = argparse.ArgumentParser(description="Ozon Orders History API client")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(func=cmd_health)

    pi = sub.add_parser("items", help="list/search/count orders")
    pi.add_argument("--q", help="search substring in title")
    pi.add_argument("--limit", type=int, default=50, help="page size (max 200; ignored with --all)")
    pi.add_argument("--cursor", help="start cursor (id) for a single page")
    pi.add_argument("--all", action="store_true", help="fetch every page")
    pi.add_argument("--status", choices=["delivered", "in progress", "cancelled"], help="filter by status")
    pi.add_argument("--returned", action="store_true", help="only returned items")
    pi.add_argument("--count", action="store_true", help="print only the count")
    pi.add_argument("--json", action="store_true", help="raw JSON output")
    pi.set_defaults(func=cmd_items)

    ps = sub.add_parser("stats", help="spending statistics")
    ps.add_argument("--granularity", choices=["year", "month", "week"], default="month")
    ps.add_argument("--from", dest="from", help="YYYY-MM-DD lower bound")
    ps.add_argument("--to", help="YYYY-MM-DD upper bound")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=cmd_stats)

    pm = sub.add_parser("image", help="download a product image")
    pm.add_argument("file", help="image filename or imageUrl path")
    pm.add_argument("-o", "--out", help="output path")
    pm.set_defaults(func=cmd_image)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
