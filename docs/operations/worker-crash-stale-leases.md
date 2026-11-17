# Runbook: Worker Crash and Stale Lease Recovery

## Symptoms
- `GET /_gx/inspect/runtime` reports `status: "degraded"` with warnings such as `"<N> stale worker snapshot(s) detected"` or `"Zero active workers registered in Redis cluster"`.
- A worker appears in `cluster.workers` with `heartbeat_status: "stale"` until its `sse_lease_ttl_seconds` (`30s` default) expires.
- Jobs claimed by the crashed worker remain in `RUNNING` status in `gx:jobs:active` until their `lease_ttl_seconds` expires and `recover_stale_jobs()` runs.
- SSE session/IP slots owned by the crashed worker remain occupied until `sse_lease_ttl_seconds` expires.

## How to Diagnose
1. Inspect `GET /_gx/inspect/runtime` -> `cluster.workers` (`worker_id`, `hostname`, `pid`, `snapshot_age_seconds`, `heartbeat_status`, `active_sse_connections`).
2. Inspect `GET /_gx/inspect/jobs` -> `active_jobs` (`owner_worker_id`, `lease_remaining_seconds`, `attempt`).
3. Check OS/container supervisor logs for OOMKills (`SIGKILL` / exit `137`) or unhandled crashes.

## Relevant Endpoints and Metrics
- `GET /_gx/inspect/runtime` (`cluster.active_workers`, `cluster.stale_workers`, `cluster.workers`)
- `GET /_gx/inspect/jobs` (`active_count`, `active_jobs[].owner_worker_id`, `active_jobs[].lease_remaining_seconds`)
- `GET /_gx/inspect/sse` (`governance.operations.expired_leases`)
- Job metrics: `stale_recovered`

## Safe Recovery Procedure
1. **SSE & Observability Leases:** Wait up to `RADUI_SSE_LEASE_TTL_SECONDS` (`30s` default). Redis `TIME`-based `ZREMRANGEBYSCORE` in `_ADMIT_LUA` automatically prunes expired SSE slots, and Redis TTL expires `gx:obs:worker:{dead_worker_id}`.
2. **Orphaned Jobs:** Ensure at least one healthy worker is running and invoke `recover_stale_jobs()` (which runs on worker job processing or manually via an admin/maintenance script using `RedisJobBackend.recover_stale_jobs()`).
3. Restart the crashed worker process; it will register a new `worker_id` on startup.

## What NOT to Do
- **Do NOT** manually `DEL` `gx:jobs:lock:{job_id}` while `lease_remaining_seconds > 0` unless you have confirmed the owning `pid` on `hostname` is dead — deleting an active lock can cause concurrent duplicate job execution.
- **Do NOT** delete `gx:gov:sse:session:*` keys directly; let Lua lease pruning or graceful `close_all()` remove only the dead worker's members.

## Verification After Recovery
1. Dead `worker_id` disappears from `GET /_gx/inspect/runtime` `cluster.workers` after TTL expiration.
2. `stale_workers == 0` and `status == "healthy"`.
3. Orphaned jobs transition back to `QUEUED` (or `FAILED` if `max_retries` exhausted) and complete on healthy workers.

## Known Limitations
- Capacity held by a `SIGKILL`ed worker cannot be reclaimed before `sse_lease_ttl_seconds` (SSE) or `lease_ttl_seconds` (jobs) expires.
- Job execution is at-least-once; if a worker crashes after side effects but before marking `SUCCEEDED`, recovery re-runs the handler.
