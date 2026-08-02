# ADR-009: Query Cache Consistency, Singleflight Deduplication & Invalidation

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
High-traffic user interfaces often make frequent data queries (e.g. user profiles, account summaries, live metric dashboards). Without caching, backend services suffer from query stampedes.

However, naive caching introduces severe consistency bugs:
- Concurrent requests for the same uncached query can trigger duplicate database calls (cache stampede).
- A slow query response completing after a subsequent state mutation can overwrite fresh data with stale results (invalidation race).
- Queries executed across organizational tenants can leak sensitive data if cache keys share a flat namespace.

## Decision

### 1. Tenant-Partitioned Cache Ownership
- Every query cache key is partitioned by tenant ID:
  $$\text{effective\_key} = \begin{cases} f"\{tenant\_id\}:\{key\}" & \text{if tenant\_id is present} \\ key & \text{otherwise} \end{cases}$$
- Cross-tenant cache lookups and invalidations are physically impossible under this prefixing model.

### 2. Singleflight Concurrent Fetch Deduplication
- When multiple concurrent requests in the same process request the same query key before a cached result exists, RADUI executes exactly one fetcher call:
  - The first caller registers an asynchronous flight task in `_inflight_queries[key]`.
  - Subsequent callers join and await the existing task rather than dispatching duplicate network requests.
  - Upon completion or failure, the flight task is removed from the active map, and the result is broadcast to all waiting callers.

### 3. Invalidation Races & Stale Response Prevention
- Each query key maintains a monotonic generation counter (`generation: int`).
- When `gx.invalidate_query(key)` is invoked:
  1. The cached entry is cleared immediately.
  2. The key's generation counter is incremented atomically (`generation = generation + 1`).
- When an asynchronous background fetch completes, it compares its captured generation with the current key generation:
  - If `captured_generation == current_generation`: the result is committed to cache.
  - If `captured_generation < current_generation`: the result is recognized as superseded by a concurrent invalidation and is silently discarded.

### 4. SWR (Stale-While-Revalidate) Contract
- If a cached entry is present and within its TTL, it is returned immediately.
- If an entry has exceeded its freshness window but is within its SWR grace period:
  - The stale entry is returned immediately to the client to preserve UI responsiveness.
  - An asynchronous revalidation task is dispatched in the background under singleflight deduplication to refresh the cache.

## Consequences
- **Positive:** Eliminates cache stampedes via singleflight deduplication.
- **Positive:** Prevents stale data overwrites via monotonic generation validation.
- **Positive:** Hard tenant isolation on all query keys.
- **Trade-off:** Applications must call `gx.invalidate_query()` when underlying business data is mutated.
