# Property Revenue Dashboard — Investigation and Fixes

## Summary

I investigated the reported revenue accuracy and privacy problems and fixed four
issues:

1. Cross-tenant revenue cache contamination.
2. Cross-tenant property-name exposure in the frontend.
3. Incorrect monthly boundaries for properties in different time zones.
4. Loss of financial precision at the API boundary.

I also fixed the local asynchronous PostgreSQL connection setup so the supplied
Docker environment can execute the revenue queries.

## 1. Cross-tenant revenue cache contamination

### Root cause

The Redis key contained only `property_id`:

```python
revenue:{property_id}
```

Property IDs are not globally unique. Both tenants have a `prop-001`, so a
cached response produced for one tenant could be returned to the other tenant.

### Fix

The authenticated tenant is now part of the cache namespace:

```python
revenue:{tenant_id}:{property_id}
```

The revenue query already filters by both `property_id` and `tenant_id`.

## 2. Cross-tenant property-name exposure

### Root cause

The frontend used one hard-coded list containing properties from both tenants.
Consequently, Ocean Rentals could see names belonging to Sunset Properties.

### Fix

I added an authenticated `/api/v1/dashboard/properties` endpoint. It derives the
tenant from the authenticated user and queries properties with:

```sql
WHERE tenant_id = :tenant_id
```

The dashboard now loads its selector from this endpoint instead of using a
shared hard-coded list.

## 3. Timezone-correct monthly revenue

### Root cause

The monthly calculation created naive datetime boundaries and returned a
placeholder value. This misclassified reservations close to a UTC month
boundary.

The seed data includes a Sunset reservation at `2024-02-29 23:30:00+00`.
For its `Europe/Paris` property, that instant is March 1 locally and belongs in
the March report.

### Fix

The calculation now:

1. Loads the property's timezone using both property and tenant IDs.
2. Creates timezone-aware start and end boundaries.
3. Filters the `TIMESTAMP WITH TIME ZONE` reservation values using those
   boundaries.
4. Returns the aggregated database result instead of a placeholder.

## 4. Financial precision

### Root cause

The API converted database `NUMERIC` values to binary floating point. Monetary
values should not depend on binary floating-point representation.

### Fix

Revenue stays as `Decimal`, is rounded once at the reporting boundary with
`ROUND_HALF_UP`, and is serialized as a fixed two-decimal string. The frontend
converts that display value only when formatting it for the UI.

## Database connection fix

The supplied Docker environment provides `DATABASE_URL`, but the connection
pool attempted to construct a URL from undefined Supabase-specific settings.
The pool now uses `DATABASE_URL`, selects the `asyncpg` driver, reuses a global
pool, and returns an async session correctly.

## Automated verification

Run:

```bash
docker compose exec backend pytest tests/test_revenue.py -q
```

Result:

```text
3 passed
```

The tests cover:

- different cache entries for tenants sharing the same property ID;
- property-local March boundaries across the daylight-saving transition;
- half-up rounding at the financial reporting boundary.

## Manual verification

The application was built and started with:

```bash
docker compose up --build -d
```

Verified results:

| Tenant | Property | Revenue | Reservations |
|---|---|---:|---:|
| Sunset Properties | Beach House Alpha (`prop-001`) | USD 2250.00 | 4 |
| Ocean Rentals | Mountain Lodge Beta (`prop-001`) | USD 0.00 | 0 |
| Ocean Rentals | Lakeside Cottage (`prop-004`) | USD 1776.50 | 4 |

The tenant-scoped property endpoint returned:

- Sunset: Beach House Alpha, City Apartment Downtown, Country Villa Estate.
- Ocean: Lakeside Cottage, Mountain Lodge Beta, Urban Loft Modern.

This confirms that tenants sharing `prop-001` receive separate revenue cache
entries and separate property lists.

## Main files changed

- `backend/app/services/cache.py`
- `backend/app/services/reservations.py`
- `backend/app/core/database_pool.py`
- `backend/app/api/v1/dashboard.py`
- `frontend/src/components/Dashboard.tsx`
- `frontend/src/components/RevenueSummary.tsx`
- `frontend/src/lib/secureApi.ts`
- `backend/tests/test_revenue.py`
