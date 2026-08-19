# Ozon Orders History — full API reference

Reverse-engineered from the running service (frontend is a Vite/React SPA that talks
to this same API). Base path: `<BASE>/api`, default `BASE=http://192.168.1.10:3027`.
No authentication. All endpoints are `GET`.

## `GET /api/health`

→ `200 {"ok": true}`. Use to confirm the service is reachable.

## `GET /api/items`

Cursor-paginated purchase list, newest first.

Params:
| param    | type   | default | notes |
|----------|--------|---------|-------|
| `q`      | string | —       | case-insensitive substring match on `title` |
| `limit`  | int    | 50      | **max 200** — `limit>200` yields `{"items":[],"nextCursor":null}` (silent empty, not an error) |
| `cursor` | int    | —       | the `nextCursor` from the prior response; returns items strictly older |

Item shape:
```json
{
  "id": 6407,                       // internal row id; also the cursor value
  "orderId": "30588125-1758",       // Ozon order number
  "orderDate": "2026-05-23",        // YYYY-MM-DD
  "position": 0,                    // line position within the order
  "title": "…",                     // product name
  "price": 678,                     // integer RUB
  "imageUrl": "/api/images/7696265572.jpg",  // relative; prepend BASE
  "productUrl": null,               // often null
  "quantity": 1,
  "status": "in progress",          // "delivered" | "in progress" | "cancelled"
  "returned": true                  // was the item returned
}
```
Response envelope: `{"items": [...], "nextCursor": <id|null>}`. `nextCursor` is
`null` on the last page.

Notes / gotchas:
- No server-side filtering by `status` or `returned` — fetch and filter client-side.
- Cursor is id-based and monotonic; the helper de-dupes by `id` as a safety net.
- To count/aggregate you must page to the end (dataset is a few thousand rows,
  spanning ~2018→present).

## `GET /api/stats`

Spending aggregated into time buckets, plus range totals.

Params:
| param         | values                    | default | notes |
|---------------|---------------------------|---------|-------|
| `granularity` | `year` \| `month` \| `week` | `month` | other values → `400 {"error":"granularity must be one of: year, month, week"}` |
| `from`        | `YYYY-MM-DD`              | all time | inclusive lower bound |
| `to`          | `YYYY-MM-DD`              | all time | inclusive upper bound |

Response:
```json
{
  "buckets": [{"period": "2026-01", "spent": 80919}],
  "totalSpent": 2793820,
  "totalReturned": 387726,
  "currency": "RUB"
}
```
`period` formatting: `2026` / `2026-01` / `2026-W03` per granularity. Totals cover
the whole selected range (all buckets), independent of bucket count. Empty buckets
(no spend in a period) are omitted rather than emitted as zero.

## `GET /api/images/<file>`

Returns the product JPEG (`Content-Type: image/jpeg`). `<file>` is the basename from
an item's `imageUrl` (e.g. `7696265572.jpg`).

## Error shape

Errors are `{"error": "<message>"}` with a 4xx status. `health` and the data
endpoints otherwise return `200`.
