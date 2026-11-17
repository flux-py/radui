# RadUI Production Deployment & Operations Guide

## 1. Configuration Reference & Precedence

Precedence order in `RadUIConfig` (`radui/core/config.py`):
**Explicit `App(...)` / `RadUIConfig` kwargs > `RADUI_*` environment variables > environment-aware defaults**.

| Environment Variable | Type | Default (`development`) | Default (`production`) | Accepted Values | Required in Prod? | Security & Behavior Notes |
|---|---|---|---|---|---|---|
| `RADUI_ENV` | `str` | `development` | `production` | `development`, `testing`, `staging`, `production` | Recommended | Enables strict production validation (`debug=False`, `session_secret`, secure cookies, inspector disabled). |
| `RADUI_DEBUG` | `bool` | `false` | `false` | `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off` | Forbidden (`false`) | `debug=True` raises `ConfigurationError` in `production`. |
| `RADUI_SESSION_SECRET` | `str` | Ephemeral random | **None (fails validation)** | String `>= 32` chars | **Yes** | Signs `radui_session` cookies (HMAC). Must be identical across all workers. Masked in logs/config. |
| `RADUI_SESSION_COOKIE_SECURE` | `bool` | `false` | `true` | Boolean | No | Sets `Secure` attribute on `radui_session` cookie (requires HTTPS in production). |
| `RADUI_SESSION_TTL_SECONDS` | `int` | `1209600` (14d) | `1209600` (14d) | Integer `>= 1` | No | Session cookie lifetime in seconds. |
| `RADUI_TRUSTED_ORIGINS` | `csv` | `""` | `""` | Comma-separated origins | If cross-origin | Allowed origins for SSE and island requests. |
| `RADUI_TRUSTED_PROXIES` | `csv` | `""` | `""` | Comma-separated proxy IPs | Behind proxy | Only proxies listed here may supply `X-Forwarded-For` for SSE IP limits. |
| `RADUI_ALLOW_UNTRUSTED_TENANT_HEADERS` | `bool` | `true` | `false` | Boolean | No | Defaults to `false` in `production`/`staging` to prevent tenant spoofing. |
| `RADUI_DRAIN_TIMEOUT` | `float` | `5.0` | `5.0` | Float `>= 0` | No | Seconds to wait for in-flight commands and background tasks on shutdown. |
| `RADUI_REQUEST_TIMEOUT` | `float` | `30.0` | `30.0` | Float `> 0` | No | Request timeout configuration (seconds). |
| `RADUI_LOG_LEVEL` | `str` | `INFO` | `INFO` | Python log levels (`INFO`, `WARNING`, etc.) | No | Controls `RedactingJsonFormatter` structured JSON log verbosity. |
| `RADUI_SSE_MAX_PER_SESSION` | `int` | `8` | `8` | Integer | No | Max concurrent SSE streams per session (`<= 0` disables cap). Global across workers in Redis mode. |
| `RADUI_SSE_MAX_PER_IP` | `int` | `32` | `32` | Integer | No | Max concurrent SSE streams per client IP (`<= 0` disables cap). Global in Redis mode. |
| `RADUI_SSE_RATE_LIMIT` | `int` | `30` | `30` | Integer | No | Max SSE connection attempts per `RADUI_SSE_RATE_WINDOW` (`<= 0` disables). |
| `RADUI_SSE_RATE_WINDOW` | `float` | `60.0` | `60.0` | Float (seconds) | No | Sliding-window duration for SSE connection rate limiting. |
| `RADUI_SSE_LEASE_TTL_SECONDS` | `float` | `30.0` | `30.0` | Float `>= 3.0` | No | TTL for Redis SSE connection leases and worker observability snapshots. |
| `RADUI_SSE_HEARTBEAT_INTERVAL_SECONDS` | `float` | `10.0` | `10.0` | Float `> 0` and `< sse_lease_ttl_seconds` | No | Interval for SSE lease renewal and observability heartbeat snapshots. |
| `RADUI_SSE_GOVERNANCE_FAIL_OPEN` | `bool` | `false` | `false` | Boolean | No | `false` fails closed (`503`) on Redis outage; `true` falls back to process-local limits. |
| `RADUI_BACKEND` | `str` | `memory` | `memory` | `memory`, `sqlite`, `redis` | For multi-worker | Must be `redis` for multi-worker deployments. |
| `RADUI_REDIS_URL` | `str` | `None` | `None` | `redis://...` or `rediss://...` | **If `backend=redis`** | Required when `RADUI_BACKEND=redis`. Credentials are masked in logs and `/_gx/inspect/config`. |
| `RADUI_SQLITE_PATH` | `str` | `None` (`RADUI_state.db`) | `None` | Filesystem path | No | SQLite WAL file path when `RADUI_BACKEND=sqlite`. Single-node only. |
| `RADUI_STATE_TTL_SECONDS` | `int` | `None` | `None` | Integer `>= 1` or unset | No | Optional Redis hash key expiration TTL for state keys. |
| `RADUI_INSPECTOR_ENABLED` | `bool` | `true` | `false` | Boolean | No | Disabled by default in `production` (`404`); requires auth + RBAC when enabled. |

---

## 2. Production Security Requirements

- **Session Secret & Cookies:** Set `RADUI_SESSION_SECRET` to at least 32 cryptographically random characters and terminate TLS so `RADUI_SESSION_COOKIE_SECURE=true` works over HTTPS.
- **Fail-Closed Defaults:** Keep `RADUI_ALLOW_UNTRUSTED_TENANT_HEADERS=false`, `RADUI_SSE_GOVERNANCE_FAIL_OPEN=false`, and `RADUI_DEBUG=false`.
- **Inspector Hardening:** Leave `RADUI_INSPECTOR_ENABLED` unset (`false`) in `production` unless troubleshooting. When enabled, all `/_gx/inspect*` routes require a valid signed session, authenticated user (`user_resolver`), and `admin` / `inspector` role or `inspect:*` permission (or custom `inspector_authorizer`).
- **Secret Redaction:** `RedactingJsonFormatter` and `redact_secrets()` mask Bearer/Basic tokens, database DSN passwords, and secret keys (`*secret*`, `*password*`, `*token*`, `*api_key*`, `*dsn*`).

---

## 3. Redis Topology, Sizing & Capacity Planning

- **Supported Topology:** Single-node Redis 7.x (`redis://` or TLS `rediss://`, standalone or primary-replica with single primary endpoint).
- **Unsupported Topology:** Redis Cluster keyspace sharding is **not supported** due to multi-key Lua scripts in `RedisSSEGovernance` and `SCAN`/`MGET` worker discovery.
- **Connection Pool Sizing:** Each worker opens up to `max_connections=32` per Redis backend (`RedisStateBackend`, `RedisEventBackend`, `RedisJobBackend`) plus 1 Pub/Sub connection per active SSE subscriber stream. Size Redis `maxclients` above `(workers * (96 + peak_sse_streams_per_worker))`.
- **Memory Planning (measured baselines on Redis 7.4.11):**
  - Worker observability snapshot (`gx:obs:worker:{id}`): `~2.8 KB` JSON (hard cap `32 KB`), expires after `sse_lease_ttl_seconds`.
  - SSE governance: 3 small ZSET entries per active stream (`session`, `ip`, `worker`) + bounded sliding-window rate-limit ZSET.
  - Event history: bounded per session by `history_size` (`128` entries default).
  - State keys: set `RADUI_STATE_TTL_SECONDS` (e.g., `86400`) if sessions should auto-expire in Redis.

---

## 4. Deployment Topologies

### Uvicorn (Single Process — Linux / Windows)
```bash
export RADUI_ENV=production
export RADUI_SESSION_SECRET="replace-with-32-plus-char-random-secret"
export RADUI_BACKEND=redis
export RADUI_REDIS_URL="rediss://:password@redis.internal:6380/0"
uvicorn app:app.asgi --factory --host 0.0.0.0 --port 8000 --proxy-headers
```

On Windows PowerShell:
```powershell
$env:RADUI_ENV = "production"
$env:RADUI_SESSION_SECRET = "replace-with-32-plus-char-random-secret"
$env:RADUI_BACKEND = "redis"
$env:RADUI_REDIS_URL = "redis://127.0.0.1:6379/0"
uvicorn app:app.asgi --factory --host 0.0.0.0 --port 8000 --proxy-headers
```

### Gunicorn with Uvicorn Workers (Linux / POSIX Multi-Worker)
```bash
gunicorn "app:app.asgi()" -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000 --graceful-timeout 10
```
*Windows Note:* Gunicorn is POSIX-only. On Windows, run multiple independent `uvicorn` worker processes on distinct ports behind Nginx/reverse proxy with `RADUI_BACKEND=redis`.

### Docker Example
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/radui-*.whl uvicorn
COPY app.py .
ENV RADUI_ENV=production
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app:app.asgi", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
```

### Nginx Reverse Proxy, TLS Termination & SSE
```nginx
upstream radui_workers {
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/ssl/certs/app.crt;
    ssl_certificate_key /etc/ssl/private/app.key;

    location / {
        proxy_pass http://radui_workers;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Required for SSE (/_gx/events)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```
Set `RADUI_TRUSTED_PROXIES="127.0.0.1"` so `X-Forwarded-For` is trusted only from Nginx.

---

## 5. Health Probes, Readiness & Graceful Shutdown

- **Liveness (`GET /health`):** Returns `200 {"status":"healthy","version":"1.0.0"}` while the process is alive; returns `503 {"status":"draining"}` during shutdown. Does **not** fail when Redis is unreachable.
- **Readiness (`GET /ready`):** Returns `200 {"status":"ready"}` only after startup completes and all readiness checks pass. When `RADUI_BACKEND=redis`, RadUI automatically registers `_default_redis_readiness_check` to probe state/event/job Redis connectivity with bounded, cooldown-protected (`0.5s`) reconnection.
- **Graceful Shutdown (`lifespan`):**
  1. Sets `_shutting_down = True` and `_ready = False`.
  2. Calls `EventBroker.close_all()` (sends `reset` to local SSE streams and immediately releases owned Redis SSE leases).
  3. Cancels background tasks (lease renewal and observability heartbeat) and drains in-flight commands up to `RADUI_DRAIN_TIMEOUT`.
  4. Runs shutdown hooks, shuts down `jobs`, deregisters `gx:obs:worker:{worker_id}`, and closes backend pools.

---

## 6. Static Site Generation (SSG) Deployment

For static or hybrid-island sites, build deterministic artifacts with:
```bash
radui build app:app --output dist --base-url https://app.example.com
```
- Emits content-hashed shared CSS (`BASE_CSS`) and JS (`CLIENT_JS`) assets, `build_manifest.json`, `islands_manifest.json`, `sitemap.xml`, and `robots.txt` using atomic staging + rollback promotion.
- Serve `dist/` from any CDN or static web server (Nginx, S3/CloudFront, Caddy).

---

## 7. Operational Runbooks & Further Reading

- [Distributed Runtime Architecture](distributed.md)
- [Observability & Diagnostics Guide](observability.md)
- Runbooks:
  - [Redis Outage & Recovery](operations/redis-outage-recovery.md)
  - [Worker Crash & Stale Lease Recovery](operations/worker-crash-stale-leases.md)
  - [Job Retries & Dead-Letter Queue Investigation](operations/job-retries-dlq.md)
  - [SSE Connection Storms & Admission Rejection](operations/sse-connection-storms.md)
  - [Readiness Failures](operations/readiness-failures.md)
  - [Observability & Diagnostics Troubleshooting](operations/observability-diagnostics.md)
