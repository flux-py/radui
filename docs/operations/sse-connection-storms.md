# Runbook: SSE Connection Storms and Admission Rejection

## Symptoms
- Clients receive HTTP `429 Too Many Requests` ("SSE connection rate limit exceeded", "Too many concurrent SSE connections for session", or "Too many concurrent SSE connections for IP") or HTTP `503` ("SSE governance backend unavailable" / "Worker SSE connection capacity reached").
- `GET /_gx/inspect/sse` shows rising `rejected_connections`, `connection_limit_violations`, `rate_limit_violations`, or `governance.operations.rejected_*`.

## How to Diagnose
1. Call `GET /_gx/inspect/sse` and inspect `governance.operations`:
   - `rejected_rate_limit`: reconnect storm or rapid client polling loop.
   - `rejected_session_limit`: too many tabs/streams sharing one `radui_session`.
   - `rejected_ip_limit`: many clients behind a NAT or misconfigured `RADUI_TRUSTED_PROXIES` (all clients seen as proxy IP!).
   - `rejected_backend_unavailable`: Redis outage with `RADUI_SSE_GOVERNANCE_FAIL_OPEN=false`.
2. Inspect `local.session_groups` (top 20 SHA-256 truncated `session_hash` counts) to see if a single session is dominating streams.
3. Check `GET /_gx/inspect/runtime` -> `cluster.workers[].active_sse_connections` for uneven load or stale leases.

## Relevant Endpoints and Metrics
- `GET /_gx/inspect/sse` (`metrics.rejected_connections`, `metrics.connection_limit_violations`, `metrics.rate_limit_violations`, `governance.operations`, `governance.latencies.admit`)
- `GET /_gx/inspect/runtime` (`cluster.sse_governance`, `cluster.workers[].active_sse_connections`)

## Safe Recovery Procedure
1. **Misconfigured Proxy IP:** If all clients share the reverse proxy's IP, set `RADUI_TRUSTED_PROXIES` to the proxy IP(s) and ensure Nginx forwards `X-Forwarded-For`.
2. **Legitimate High Concurrency Behind Shared Corporate NAT:** Increase `RADUI_SSE_MAX_PER_IP` (e.g., from `32` to `128`) or `RADUI_SSE_RATE_LIMIT` / `RADUI_SSE_RATE_WINDOW`.
3. **Abusive Client / Reconnect Loop:** Keep `RADUI_SSE_GOVERNANCE_FAIL_OPEN=false` and enforce edge rate-limiting in Nginx/WAF.
4. **Redis Outage:** Follow [Redis Outage & Recovery](redis-outage-recovery.md).

## What NOT to Do
- **Do NOT** set `RADUI_SSE_MAX_PER_SESSION=0` and `RADUI_SSE_MAX_PER_IP=0` in production without edge rate limiting — this exposes workers to file-descriptor and memory exhaustion.
- **Do NOT** manually `DEL gx:gov:sse:*` keys during live traffic; this causes temporary over-admission and desynchronizes worker registries.

## Verification After Recovery
1. `GET /_gx/inspect/sse` shows `rejected_rate_limit` / `rejected_ip_limit` stabilizing and `admitted` succeeding.
2. `governance.operations.renewal_failures` remains `0`.

## Known Limitations
- Session identifiers in `local.session_groups` are hashed (`sha256[:12]`) and capped at 20 groups per worker for privacy and bounded responses.
