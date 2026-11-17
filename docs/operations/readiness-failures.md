# Runbook: Readiness Failures

## Symptoms
- Load balancer / Kubernetes readiness probe (`GET /ready`) returns `503 {"status": "not_ready", "version": "1.0.0"}` and stops routing traffic to the worker.
- `GET /health` may still return `200 {"status": "healthy"}` (unless the worker is shutting down, in which case it returns `503 {"status": "draining"}`).

## How to Diagnose
1. Check `GET /health` first:
   - If `/health` is `503 {"status": "draining"}`: the worker is in graceful shutdown (`_shutting_down=True`).
   - If `/health` is `200`: the process is alive, and either startup failed (`_ready=False`), `_default_redis_readiness_check` failed, or a custom `add_readiness_check()` returned `False`/raised.
2. Check worker startup logs (`app.startup_error`) for configuration or backend connectivity failures.
3. If `RADUI_BACKEND=redis`, check `GET /_gx/inspect/runtime` (`redis.connected`, `redis.error`, `warnings`) or test Redis directly.

## Relevant Endpoints and Metrics
- `GET /health` (`status`: `"healthy"` or `"draining"`)
- `GET /ready` (`status`: `"ready"` or `"not_ready"`)
- `GET /_gx/inspect/runtime` (`redis.connected`, `redis.ping_ms`, `warnings`)

## Safe Recovery Procedure
1. If `app.startup_error` indicates `ConfigurationError` (e.g., missing `RADUI_SESSION_SECRET` or `RADUI_REDIS_URL`, or `RADUI_DEBUG=true` in `production`), fix the environment configuration and restart the worker.
2. If Redis is down, restore Redis connectivity; subsequent `/ready` probes (spaced by at least `0.5s`) will trigger `_probe_and_recover_redis()` and return `200`.
3. If a custom user readiness check is failing, resolve the downstream dependency it monitors.

## What NOT to Do
- **Do NOT** point load-balancer traffic readiness probes at `/health` instead of `/ready` for Redis-backed apps — `/health` intentionally stays `200` during Redis outages and would route traffic to workers that cannot read/write state.
- **Do NOT** disable `_default_redis_readiness_check` in production.

## Verification After Recovery
1. `GET /ready` returns `200 {"status": "ready"}`.
2. Load balancer marks the worker healthy and resumes routing traffic.

## Known Limitations
- `_probe_and_recover_redis()` enforces a `0.5s` cooldown between reconnect attempts; probes arriving within `0.5s` of a failed reconnect return `503` immediately without opening new Redis sockets.
