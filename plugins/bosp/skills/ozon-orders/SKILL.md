---
name: ozon-orders
description: >
  Query the "Ozon Orders History" service — a personal read-only API over one's
  Ozon (ozon.ru) purchase history. Use to look up past orders/purchases, search
  items by title, see order status (delivered / in progress / cancelled), find
  returned items, download product images, and get spending statistics
  (totals + per year/month/week breakdown, with the returned amount).
when_to_use: >
  Trigger on questions about Ozon purchases / order history / что заказывали на
  Озоне / сколько потрачено на Ozon / возвраты / spending on Ozon, or any request
  to search, list, count, or aggregate this person's Ozon orders. Also: "ozon
  orders", "ozon history", "Ozon Orders History", "сколько я потратил на озоне".
allowed-tools: Bash
---

# Ozon Orders History API

A small self-hosted service that exposes one person's Ozon purchase history as a
read-only JSON API. There is **no auth** — it is reachable on the local network.
This skill lets you answer questions about their orders, returns, and spending by
calling that API.

## Base URL

Default: `http://192.168.1.10:3027`

Override with the `OZON_HISTORY_BASE` environment variable if the host/port differs.
The API is mounted under `/api`.

## Quick start

Use the bundled helper for anything non-trivial (it handles cursor pagination):

```bash
python3 ~/.claude/skills/ozon-orders/ozon.py health
python3 ~/.claude/skills/ozon-orders/ozon.py items --q "нори" --all
python3 ~/.claude/skills/ozon-orders/ozon.py stats --granularity year
```

For one-off reads a plain `curl` is fine too:

```bash
curl -s "http://192.168.1.10:3027/api/items?limit=5"
curl -s "http://192.168.1.10:3027/api/stats?granularity=month&from=2026-01-01&to=2026-06-01"
```

## Endpoints (this is the whole API)

| Method & path        | Purpose                                  |
|----------------------|------------------------------------------|
| `GET /api/health`    | Liveness → `{"ok":true}`                 |
| `GET /api/items`     | Orders/purchases, cursor-paginated       |
| `GET /api/stats`     | Spending aggregated into time buckets    |
| `GET /api/images/<file>` | Product image (JPEG)                 |

### `GET /api/items`

Query params (all optional):
- `q` — free-text search over the item title (case-insensitive substring).
- `limit` — page size. Default `50`, **max `200`**. A value > 200 returns an
  **empty** `items` array (not an error) — never exceed 200; page instead.
- `cursor` — pass the `nextCursor` from the previous response to get older items.

Newest orders come first; paging walks backwards in time. Response:

```json
{
  "items": [
    {
      "id": 6407,
      "orderId": "30588125-1758",
      "orderDate": "2026-05-23",
      "position": 0,
      "title": "Смесь сухофруктов 1000 гр. ... Narmak",
      "price": 678,
      "imageUrl": "/api/images/7696265572.jpg",
      "productUrl": null,
      "quantity": 1,
      "status": "in progress",
      "returned": true
    }
  ],
  "nextCursor": 6406
}
```

- `status` is one of: `"delivered"`, `"in progress"`, `"cancelled"`.
- `returned` is a boolean — `true` means the item was returned.
- `price` is in rubles (integer). `imageUrl` is a relative path under the base URL.
- `nextCursor` is `null` on the last page.

There is **no server-side filter** for `status` or `returned` — filter client-side
(the helper's `--status` / `--returned` flags do this over the fetched pages).

### `GET /api/stats`

Query params:
- `granularity` — one of `year`, `month`, `week`. Default `month`. Any other value
  (e.g. `day`, `quarter`) returns `{"error":"granularity must be one of: year, month, week"}`.
- `from`, `to` — inclusive `YYYY-MM-DD` date bounds (optional; omit for all time).

Response:

```json
{
  "buckets": [{"period": "2026-01", "spent": 80919}, ...],
  "totalSpent": 2793820,
  "totalReturned": 387726,
  "currency": "RUB"
}
```

Period format depends on granularity: `2026` (year), `2026-01` (month), `2026-W03`
(ISO week). `totalSpent` / `totalReturned` are over the whole selected range, not
per bucket.

## Answering guidance

- Report money in rubles (₽) — the API already returns integer RUB.
- For "how much did I spend / on returns" use `stats` totals; don't sum `items`.
- For "how many orders of X" / "did I ever buy Y" use `items --q ... --all` and count.
- The dataset spans ~2018→present and is a few thousand items; always `--all` (or
  page manually with `cursor`) when counting or aggregating, or you only see 50.
- See `references/api.md` for edge cases (limits, cursor semantics, error shapes).
