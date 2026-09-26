# Wiring the hawker dashboard to this service

**The integration is done** and verified end to end on 2026-09-27: the hawker
dashboard reads its figures from this service. The work is on the `hawker-ui`
branch `analytics-integration`.

This document describes the contract and explains what changed, so the next
person to touch the analytics screen knows what it now depends on. If you are
reviewing that branch, the "What changed" section below is the summary.

## What changed on the dashboard

`hawker-ui`'s analytics screen used to compute its figures in the browser from
`OrderService.orders`. Those numbers came from whatever orders happened to be
loaded in the tab, and four of them were not real:

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

## How the Angular side is built

`AnalyticsApiService` returns an `Observable`, not a `Promise` — unlike
`OrderApiService` — so `AnalyticsService` can cancel a stale request with
`switchMap`. Without that, a slow response for a previously selected stall or
date can overwrite the figures currently on screen.

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
integer. The id is read from `StallAccount.numericId`, falling back to the
session's `numericStallId`. Both come from `backendStall.stall_id`, so neither
is a guess.

The session fallback matters because `AuthService.currentStall` resolves against
`allStalls()`, which is filled only by a fetch from the hawker service. With
that service down, `currentStall()` is null even for a validly signed-in user,
and analytics needs nothing else from it.

With neither id present the screen shows a setup message. It **never infers an
id from array position and never falls back to stall 1** — that would silently
show one stall another stall's takings.

An earlier draft of this document proposed a hardcoded key-to-id map in
`environment.ts`. That was dropped: `numericId` is populated from the backend at
login, so a configured map would be a strictly worse source of truth.

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

## Verified

Checked against the running stack on 2026-09-27, stall 1 on 2026-09-26:

- The dashboard shows $63.30 across 5 completed orders, matching the same
  figures computed directly in SQL, and the top-dish values sum to the total —
  so dish rows are not double-counted.
- The figures appear on navigating to the screen, without first visiting KDS or
  Orders. That was the original defect: the screen never fetched anything.
- A day with no orders shows zeros and "No completed orders", not an error.
- With the analytics service stopped, Refresh shows an error and a Retry
  button, and **no figures at all** — no stale values linger and nothing falls
  back to browser-computed numbers. Retry recovers once the service returns.
- Another stall does not see stall 1's takings.

## Two defects found and fixed along the way

Both in `hawker-ui`, both outside analytics, both on the same branch:

- **The analytics screen never fetched.** It read whatever `OrderService`
  already held, which is empty on load, so it showed zeros unless the user had
  visited KDS or Orders first.
- **Backend-registered stalls could not sign in.**
  `mapBackendStallToAccount` left `username` undefined and discarded the
  owner's email, while the local login matched only on `username`. No typed
  value could ever match, so registering a stall through the hawker service
  produced an account nobody could use.

Related: the hawker service stores no credentials at all, so the local login
accepts any password for a backend-registered stall. That is tolerable on a
loopback development stack and must not reach a deployed environment.

## Questions

The contract is settled but not frozen. If the dashboard needs a field that is
not here — a date range rather than a single day, say, or per-dish revenue
ranking — raise it rather than computing it in the browser. Adding it here keeps
one definition of what a number means.
