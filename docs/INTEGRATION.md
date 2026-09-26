# Wiring the hawker dashboard to this service

For whoever owns `hawker-ui`. This service is finished and tested; the frontend
side is deliberately left for you, because the analytics screen is yours.

## What changes on your side

`hawker-ui`'s analytics screen currently computes its figures in the browser,
from `OrderService.orders`. Those numbers are derived from whatever orders
happen to be loaded in the tab, and four of them are not real:

| Card today | Reality |
|---|---|
| Avg Prep Time `4.2 mins` | Hardcoded fallback. The order schema has no preparation timestamps. |
| Payment breakdown (PayNow/cash/NETS/card) | The order schema stores no payment method. |
| Takeaway fees | Not captured on orders. |
| Shift Close Z-Report | There is no shift record. |

Two of those are worth spelling out, because the screen looks convincing.

`OrderService.backendToFrontendOrder` hardcodes `paymentMethod: 'paynow'` and
`takeawayFee: 0` on every order it builds from the backend — the DTO has no such
fields. So the payment breakdown reads **100% PayNow** for every stall, every
day, and takeaway fees read `$0.00`. Neither is a measurement; both are defaults
being charted. `avgPrepTimeMins` falls back to a literal `4.2` when no
timestamps exist, which is always.

**Gross Sales is correct** and this service does not change how it is computed.
`getStallOrders` returns stall-level `subtotal`, so the figure is already scoped
to one stall.

The real limitation is scope, not arithmetic: everything is derived from
`OrderService.orders`, the orders loaded in that browser tab. Refresh and the
shift summary is whatever reloads. This service computes the same figures in
PostgreSQL instead, so they persist and are identical on every device.

## The endpoint

```
GET http://localhost:8083/hawkerflow/v1/analytics/stalls/{stallId}/summary?date=YYYY-MM-DD
Header: X-Stall-ID: {stallId}      # must match the path
```

`date` is optional and defaults to today's Singapore date.

```json
{
  "stallId": 1,
  "date": "2026-09-26",
  "timezone": "Asia/Singapore",
  "source": "postgresql",
  "totalOrders": 5,
  "completedOrders": 5,
  "cancelledOrders": 0,
  "completedOrderValue": 63.30,
  "averageCompletedOrderValue": 12.66,
  "topItems": [
    { "dishId": 2, "name": "Iced Kopi", "quantity": 6, "completedItemValue": 10.80 }
  ],
  "hourlyOrders": [{ "hour": 0, "orderCount": 0, "completedOrderValue": 0.0 }],
  "unavailableMetrics": [
    "paymentBreakdown", "preparationTime", "takeawayFees", "shiftClosure"
  ]
}
```

Three things to build against:

- `hourlyOrders` always has **exactly 24 entries**, hours `0`-`23` in Singapore
  time, present even when zero. Scale your chart to the max count, not to a
  fixed value.
- `averageCompletedOrderValue` is **`null`** when nothing completed. Not `0` —
  zero would read as a measurement. Render "No completed orders" for null.
- `completedOrderValue` is this stall's share only, already rounded to two
  places. Do not round it again.

| Status | Meaning | What the UI should do |
|---|---|---|
| 200 | Success. No orders returns zeros, not an error. | Show the figures, including confident zeros. |
| 401 | `X-Stall-ID` missing or malformed | Fix the request; this is a bug, not a user state. |
| 403 | `X-Stall-ID` does not match the path | Same. |
| 422 | Invalid stall id or date | Validate before sending. |
| 503 | Database unavailable | Show an error with a Retry button. **Never fall back to browser figures.** |

## Suggested Angular shape

Return an `Observable`, not a `Promise`, so a slow response for a previously
selected stall cannot overwrite the current one:

```typescript
@Injectable({ providedIn: 'root' })
export class AnalyticsApiService {
  private http = inject(HttpClient);
  private baseUrl = environment.analyticsApiUrl;   // http://localhost:8083/hawkerflow

  getStallDaySummary(stallId: number, isoDate: string): Observable<StallDaySummary> {
    return this.http.get<StallDaySummary>(
      `${this.baseUrl}/v1/analytics/stalls/${stallId}/summary`,
      {
        headers: new HttpHeaders().set('X-Stall-ID', String(stallId)),
        params: new HttpParams().set('date', isoDate),
      }
    );
  }
}
```

Then cancel stale requests with `switchMap`:

```typescript
this.requests.pipe(
  switchMap(req => this.api.getStallDaySummary(req.stallId, req.isoDate))
).subscribe(/* ... */);
```

## Stall ids

The frontend uses string keys (`stall-ah-huat`); this service takes the backend
integer. `StallAccount.numericId` already exists in `auth.model.ts`. Use an
explicit configured mapping — **never infer an id from array position, and never
fall back to stall 1**, or one stall will silently show another's takings. A
stall with no configured id should show a setup message.

## What feeds it

Only orders **persisted through the order service API**. Orders that live only
in browser state never reach this service, so the dashboard will not match a
POS session that was never submitted. Worth saying in the UI.

## Running it locally

See [RUN_LOCALLY.md](RUN_LOCALLY.md). Short version: PostgreSQL container up,
order service tables created, read-only role created, then `make run`. It binds
to `127.0.0.1:8083` and accepts browser requests from `http://localhost:4200`
only.

Sanity check without the UI:

```bash
curl -s -H "X-Stall-ID: 1" \
  "http://127.0.0.1:8083/hawkerflow/v1/analytics/stalls/1/summary" | python -m json.tool
```

To get numbers to look at:

```bash
python scripts/seed_sample_orders.py --stall 1 --orders 5
```

## Questions

The contract is settled but not frozen. If the dashboard needs a field that is
not here — a date range rather than a single day, say, or per-dish revenue
ranking — raise it rather than computing it in the browser. Adding it here keeps
one definition of what a number means.
