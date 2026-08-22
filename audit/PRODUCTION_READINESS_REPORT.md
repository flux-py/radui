# RADUI Framework: Production Readiness & Chaos Engineering Report

**Audit Date:** November 2026  
**Auditor:** Principal Site Reliability Engineer (SRE) & Chaos Architect  
**Target:** RADUI UI (`RADUI-ui`) v0.9.0  
**Status:** APPROVED FOR IMPLEMENTATION PLANNING  
**Methodology:** Failure injection, microbenchmarks, lease concurrency tests, and deployment review

---

## 1. Production Readiness Scorecard

| Domain | Production Grade | Risk Level | Reconciled Assessment |
|---|---|---|---|
| **Single-Node Deployment** | **Partially Verified (Conditional)** | Low / Medium | Robust for single-host deployments using SQLite WAL mode with low-write concurrency (<500 writes/sec). Risk: Unbounded in-memory event queues and session loss on default memory backend. |
| **Multi-Node Cluster** | **Unverified / Incomplete** | High | Redis state, events, and idempotency are functional. However, `PostgreSQLStateBackend` and `PostgreSQLEventBackend` are stubs. `RedisJobBackend` keeps task queues in local memory. True distributed clustering is unverified. |
| **Security & Hardening** | **B (Needs Tenant Hardening)** | Medium | Encrypted session cookies, automatic CSRF validation, XSS escaping, and rate limiting work. However, multi-tenancy currently lacks fail-closed enforcement and leaves cache, jobs, chat, and outbox unpartitioned (ADR 003). |
| **Observability & SRE** | **A- (Strong)** | Low | Built-in OpenTelemetry (OTLP) exporter, execution collector, DAG visualizer, and Prometheus-compatible stats. |
| **Failure Recovery & Chaos** | **B (Solid)** | Medium | Fencing tokens protect against zombie worker writes; outbox leases provide at-least-once delivery; `ErrorBoundary` isolates UI crashes. |

---

## 2. Chaos Engineering & Failure Mode Analysis

### 2.1. Scenario 1: Sudden Server Crash & Restart
- **Observation:**
  - With default `InMemoryStateBackend`, all user sessions and reactive state are wiped instantly. Active browser clients receive disconnect errors.
  - With `SQLiteStateBackend`, all session, user, and app state persist on disk across restarts.
  - Active background jobs in `LocalJobBackend` that were executing during the crash are lost. With `SQLiteJobBackend`, leases expire, and orphaned jobs can be recovered.

### 2.2. Scenario 2: Database Outage & Latency Spikes
- **Observation:**
  - In `gx.query()`, external database queries run in background worker threads with configurable `retry` and `stale_time`.
  - If the database fails, cached data continues to be served (Stale-While-Revalidate pattern), preventing user-facing 500 errors during temporary database downtime.
  - If a distributed state backend (Redis) is unreachable and `allow_fallback=False` is set, RADUI immediately raises `StateBackendUnavailableError` to prevent split-brain data corruption.

### 2.3. Scenario 3: LLM API Outages & Stream Interruption
- **Observation:**
  - `RADUI.ai.streaming` streams tokens over SSE. If the upstream LLM API drops the connection mid-stream, `StreamingText` retains all previously emitted tokens and sets status to interrupted.
  - `SQLiteChatRepository` commits messages upon completion, preventing partial corrupted JSON payloads.

### 2.4. Scenario 4: Slow Clients & SSE Backpressure
- **Observation:**
  - When an SSE client experiences high latency or pauses TCP read, `InMemoryEventBackend` buffers events in per-session queues.
  - **Identified Defect:** Unbounded queue growth. If a slow client remains connected for hours under heavy server event emission, memory consumption grows linearly. **A bounded ring-buffer (e.g. 500 events) with drop-oldest policy is required for v1.0.0.**

### 2.5. Scenario 5: High-Concurrency Burst & Throttling
- **Observation:**
  - `RateLimiter` enforces sliding-window limits per client IP (e.g. 60 RPM + burst allowance).
  - Burst traffic exceeding the threshold receives HTTP 429 Too Many Requests with a `Retry-After` header.

### 2.6. Scenario 6: Malformed Input & Security Attacks
- **Observation:**
  - **XSS:** All text nodes and string bindings are automatically escaped with `html.escape()`.
  - **CSRF:** Every form submission includes a cryptographically signed CSRF token tied to the session cookie. Missing or invalid tokens reject requests with HTTP 403.
  - **Tenant Boundary Leakage:** Currently partitioned only for state keys. Full internal propagation across QueryCache, Jobs, Chat, Outbox, and Events is required by ADR 003.

---

## 3. Production Deployment Guidelines (Single-Node Focus)

### 3.1. Infrastructure & OS Requirements
- Python 3.10+ (Verified on Python 3.12.10)
- Operating Systems: Linux (Ubuntu 22.04+, Debian 12+), macOS, Windows Server
- ASGI Web Servers: Uvicorn, Gunicorn (`uvicorn.workers.UvicornWorker`), Granian
- Reverse Proxy: Nginx, Caddy, Cloudflare, Traefik (must support unbuffered SSE streaming: `proxy_buffering off;`)

### 3.2. Mandatory Single-Node Production Configuration
```python
# Production Configuration Pattern (Single-Node SQLite WAL)
app = gx.App(
    "Enterprise Production Portal",
    app_id="enterprise-prod",
    debug=False,                                # MUST be False in production
    secret_key=os.environ["SECRET_KEY"],        # 32+ byte cryptographic random secret
    session_cookie_secure=True,                 # Enforce HTTPS-only cookie
    state_backend=gx.SQLiteStateBackend(        # Persistent SQLite WAL backend
        db_path="/var/data/RADUI_state.db"
    ),
    job_backend=gx.SQLiteJobBackend(
        db_path="/var/data/RADUI_jobs.db"
    ),
    event_backend=gx.SQLiteEventBackend(
        db_path="/var/data/RADUI_events.db"
    ),
    rate_limit_rpm=120,
    drain_timeout=15.0,
)
```

### 3.3. Key Operational Constraints
1. **Nginx Buffering:** Nginx defaults to buffering HTTP responses. For RADUI SSE events (`/_gx/events`), `X-Accel-Buffering: no` must be returned, or Nginx must be configured with `proxy_buffering off;`.
2. **SQLite Write Contention:** While SQLite WAL mode allows concurrent readers, multiple worker processes attempting concurrent writes can encounter busy timeouts under heavy write spikes (> 500 writes/sec).
3. **Delivery Semantics:** `TransactionalOutbox` provides at-least-once delivery; consumers must be idempotent.
