# Runbook: Observability and Diagnostics Troubleshooting

## Symptoms
- `GET /_gx/inspect*` returns `404 Not Found`, `401 Unauthorized`, or `403 Forbidden`.
- `GET /_gx/inspect/runtime` shows `malformed_snapshots > 0`, `stale_workers > 0`, or `unavailable` latency fields.
- Dashboard **Auto-refresh** does not appear to update within 1 second of clicking **Refresh Now**.

## How to Diagnose
1. **HTTP 404 on `/_gx/inspect*`:** `RADUI_INSPECTOR_ENABLED` is `false` (the secure default in `RADUI_ENV=production`).
2. **HTTP 401 / 403 on `/_gx/inspect*`:** Missing/invalid `radui_session` cookie (`401`), unauthenticated user (`401`), or user lacks `admin` / `inspector` role or `inspect:*` permission (`403`).
3. **`malformed_snapshots > 0`:** Another tool or incompatible version wrote non-JSON or unexpected schema keys under `gx:obs:worker:*`.
4. **`ttl_expirations.available == false`:** Expected behavior; passive Redis key expirations are not tracked without keyspace notifications.
5. **1.0s Cache Coalescing:** `DiagnosticsCollector` caches `/_gx/inspect/runtime` and `/_gx/inspect/jobs` for `1.0s` (`cache_ttl_seconds=1.0`) to protect Redis from dashboard refresh storms.

## Relevant Endpoints and Metrics
- `GET /_gx/inspect` (HTML dashboard)
- `GET /_gx/inspect/runtime` (`cluster.malformed_snapshots`, `cluster.stale_workers`, `warnings`)
- `GET /_gx/inspect/config` (redacted `RadUIConfig.safe_summary()`)

## Safe Recovery Procedure
1. **Enable Inspector Temporarily in Production:** Set `RADUI_INSPECTOR_ENABLED=true`, ensure `user_resolver` authenticates an `admin` or `inspector` user, and disable it again once troubleshooting completes.
2. **Malformed Snapshots:** Inspect keys matching `gx:obs:worker:*` with `SCAN` (`redis-cli --scan --pattern "gx:obs:worker:*"`) and `DEL` only the specific corrupt key (never `FLUSHDB`). Valid worker keys will be republished on the next `10s` heartbeat.
3. **High `publish_errors` on a Worker:** Check snapshot size (`MAX_SNAPSHOT_BYTES = 32768`) and Redis connectivity.

## What NOT to Do
- **Do NOT** leave `RADUI_INSPECTOR_ENABLED=true` in production without verified authentication (`user_resolver` or `inspector_authorizer`).
- **Do NOT** use `KEYS *` on production Redis to debug `gx:obs:worker:*`; always use `SCAN`.

## Verification After Recovery
1. Authenticated inspector receives `200` on `/_gx/inspect` and `/_gx/inspect/runtime`.
2. `cluster.malformed_snapshots == 0` and `warnings` is empty.

## Known Limitations
- `DiagnosticsCollector` scans up to `500` worker keys (`MAX_WORKERS_RETURNED = 100` in roster) and uses `SCAN`/`MGET`, which is unsupported on sharded Redis Cluster.
- Actual Redis state TTL expiration counts are unavailable and explicitly marked `available: false`.
