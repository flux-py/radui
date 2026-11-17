# Runbook: Redis Outage and Recovery

## Symptoms
- `GET /ready` returns `503 {"status": "not_ready"}` while `GET /health` remains `200 {"status": "healthy"}`.
- `GET /_gx/inspect/runtime` reports `status: "unavailable"`, `redis.connected: false`, `cluster.available: false`, and `null` gauges (`queue_depth`, `active_count`, `dlq_depth`).
- New SSE connections return `503` ("SSE governance backend unavailable") when `RADUI_SSE_GOVERNANCE_FAIL_OPEN=false`.
- State operations raise `StateBackendUnavailableError`.

## How to Diagnose
1. Check `GET /ready` and `GET /_gx/inspect/runtime` (`redis.error`, `redis.ping_ms`).
2. Check worker structured logs for `RedisStateBackend failed to connect`, `RedisEventBackend unavailable`, `RedisJobBackend unavailable`, or `RedisSSEGovernance admit failed`.
3. Verify Redis reachability from a worker host (e.g., `redis-cli -u "$RADUI_REDIS_URL" ping` or Docker `docker ps` / container logs).

## Relevant Endpoints and Metrics
- `GET /health`, `GET /ready`
- `GET /_gx/inspect/runtime` (`redis.connected`, `redis.ping_ms`, `status`)
- `GET /_gx/inspect/sse` (`governance.available`, `governance.operations.rejected_backend_unavailable`, `governance.operations.renewal_failures`, `metrics.backend_errors`)

## Safe Recovery Procedure
1. Restore the Redis server/service or resolve network/TLS/auth issues preventing workers from reaching `RADUI_REDIS_URL`.
2. Wait at least `0.5s` (the `_redis_reconnect_cooldown_seconds` guard) and poll `GET /ready` on each worker (or let Kubernetes/load-balancer readiness probes run). `_probe_and_recover_redis()` will reconnect `state_runtime.backend`, `events.backend`, and `jobs`.
3. Once Redis is back, run `recover_stale_jobs()` on an active worker if any jobs were interrupted mid-execution during the outage.

## What NOT to Do
- **Do NOT** run `FLUSHALL` or `FLUSHDB` on Redis to "reset" connections — this destroys active session state, event replay history, job records, and idempotency keys.
- **Do NOT** switch `RADUI_BACKEND=memory` in a multi-worker deployment; doing so causes cluster split-brain.
- **Do NOT** restart all workers simultaneously if Redis is already back; `/ready` probes restore client connections automatically without process restarts.

## Verification After Recovery
1. `GET /ready` returns `200 {"status": "ready"}`.
2. `GET /_gx/inspect/runtime` shows `status: "healthy"` (or `"degraded"` only until stale worker TTLs expire), `redis.connected: true`, and numeric `redis.ping_ms`.
3. Confirm new state writes, event publishes, and SSE admissions succeed.

## Known Limitations
- Existing SSE streams whose `subscribe_remote()` Pub/Sub reader exited during the outage fall back to `keepalive_seconds`-interval replay reconciliation rather than automatically re-subscribing Pub/Sub; live Pub/Sub push resumes when clients reconnect SSE.
- Redis Cluster keyspace sharding is unsupported.
