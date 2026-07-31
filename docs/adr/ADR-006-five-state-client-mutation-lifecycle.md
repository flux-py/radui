# ADR-006: 5-State Client Mutation Lifecycle, Machine-Readable Error Codes & Offline Storage Specification

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
In browser offline mutation queues, treating all HTTP errors as retryable causes severe failure storms. If a client mutation encounters HTTP 400 (Bad Request), 404 (Not Found), or 422 (Validation Error), retrying infinitely congests the client queue and overloads backend servers.

Conversely, treating HTTP 409 (Conflict) solely as a permanent error breaks the idempotency engine: when another worker is processing the same action ID, the server returns HTTP 409 with `Retry-After: 1` (`IDEMPOTENCY_IN_PROGRESS`). If the client treats all 409 responses as permanent failures, valid mutations are abandoned prematurely.

Finally, documentation inconsistently referenced two different database names (`_gx_offline_db` vs `__gx_offline_store`). A formal canonical storage specification is required.

## Decision

### 1. Canonical Storage Specification
- **Database Name:** `_gx_offline_db`
- **Database Version:** `1`
- **Object Store Name:** `mutations`
- **Primary Key:** `actionId: string` (keyPath)
- **Indexes:**
  - `timestamp`: Non-unique index on record creation time for FIFO replay ordering.
  - `status`: Non-unique index for filtering pending vs dead-letter records.
- **Fallback Storage:** `localStorage["__gx_offline_q"]` (JSON array) when IndexedDB is blocked or disabled in restricted private-browsing modes.

### 2. Machine-Readable Error Taxonomy
HTTP status codes alone are insufficient to distinguish between retryable transient states and permanent rejections. RADUI introduces structured error responses containing machine-readable `error_code` fields:

| HTTP Status | Error Code | Classification | Lifecycle Behavior |
| :--- | :--- | :--- | :--- |
| **400** | `VALIDATION_ERROR` / `MALFORMED_INPUT` | Permanent | Transition to `PERMANENT_FAILURE` |
| **401** | `AUTH_REQUIRED` | Pause | Transition to `AUTH_REQUIRED`; preserve queue |
| **403** | `FORBIDDEN` / `UNAUTHORIZED_TENANT` | Permanent | Transition to `PERMANENT_FAILURE` |
| **404** | `RESOURCE_NOT_FOUND` | Permanent | Transition to `PERMANENT_FAILURE` |
| **409** | `IDEMPOTENCY_IN_PROGRESS` | **Retryable** | Return to `QUEUED`; backoff via `Retry-After` |
| **409** | `IDEMPOTENCY_PAYLOAD_MISMATCH` | Permanent | Transition to `PERMANENT_FAILURE` (fingerprint conflict) |
| **409** | `RESOURCE_VERSION_CONFLICT` | Permanent | Transition to `PERMANENT_FAILURE` (state conflict) |
| **413** | `PAYLOAD_TOO_LARGE` | Permanent | Transition to `PERMANENT_FAILURE` |
| **422** | `SEMANTIC_VALIDATION_ERROR` | Permanent | Transition to `PERMANENT_FAILURE` |
| **429** | `RATE_LIMITED` | **Retryable** | Return to `QUEUED`; backoff via `Retry-After` |
| **500–504** | `SERVER_ERROR` | **Retryable** | Return to `QUEUED`; exponential backoff |

### 3. Canonical Five Durable States & Transition Semantics
The browser runtime `CLIENT_JS` enforces strictly five durable lifecycle states:

```
                       +-------------------+
                       |      QUEUED       |<--------------------+
                       +-------------------+                     |
                                 |                               |
                                 | (lease acquired)              | (retryable 409/429/5xx/net err)
                                 v                               |
                       +-------------------+                     |
                       |     IN_FLIGHT     |---------------------+
                       +-------------------+
                          /      |        \
                         /       |         \
         (HTTP 200/204) / (HTTP 401) (Permanent 4xx / payload mismatch / max retries)
                       /         |           \
                      v          v            v
               +---------+  +---------+  +-------------------+
               | SUCCESS |  |  AUTH_  |  | PERMANENT_FAILURE |
               +---------+  |REQUIRED |  +-------------------+
                            +---------+
```

1. `QUEUED`: Stored in IndexedDB awaiting dispatch. On retryable errors, mutations remain in `QUEUED`, recording metadata (`retries`, `lastError`, `lastStatusCode`, `nextRetryAt`).
2. `IN_FLIGHT`: Currently claimed by active replay worker under Web Lock or lease.
3. `SUCCESS`: Acknowledged by server; differential state patches applied; record deleted from queue.
4. `AUTH_REQUIRED`: Received HTTP 401 Unauthorized. Replay pauses without discarding queue until authentication is re-established.
5. `PERMANENT_FAILURE`: Terminal non-retryable failure or retries exceeded 10. Replay halts; record is moved to dead-letter storage with error telemetry for user notification and dismissal.

### 4. Cross-Tab Coordination & Fallback Protocol
- **Primary Coordination:** Web Locks API (`navigator.locks.request('_gx_replay_lock')`) guarantees single-tab execution across same-origin tabs.
- **Fallback Lease Protocol:** In browsers lacking Web Locks:
  - Tabs negotiate leases via `localStorage` keys: `_gx_replay_lease` (owner UUID), `_gx_replay_lease_exp` (heartbeat expiry timestamp), and `_gx_replay_generation` (monotonically increasing generation counter).
  - Active worker renews its lease every 2 seconds.
  - Before each network dispatch, the worker validates that its lease token and generation have not been revoked by another tab.
  - If a background tab is suspended by the browser OS and wakes up after lease expiry, the generation mismatch prevents it from dispatching obsolete requests.
- **Defense-in-Depth:** Browser-side coordination is an optimization; server-side idempotency backend is the authoritative line of defense against duplicate executions.

## Consequences
- **Positive:** Canonical database and store naming (`_gx_offline_db` / `mutations`) eliminates fragmented queues.
- **Positive:** Fine-grained error code parsing prevents in-flight idempotency conflicts from being misclassified as permanent failures.
- **Positive:** Robust fallback lease protocol protects against tab suspension split-brain anomalies.
- **Trade-off:** Permanent failure records require user inspection or explicit dismissal API calls (`window._gxQueue.clearFailed()`).
