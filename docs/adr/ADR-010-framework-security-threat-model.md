# ADR-010: Framework Security Architecture & Threat Model

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
Web application frameworks face a wide range of security threats: Cross-Site Request Forgery (CSRF), Cross-Site Scripting (XSS), session fixation, tenant spoofing, denial of service via unbounded body payloads, and path traversal in file uploads.

A production-ready framework must define an explicit threat model and implement default-secure defenses across all request pipelines.

## Decision

### 1. Threat Matrix & Mitigations

| Threat | Attack Vector | Framework Mitigation | Enforcement Level |
| :--- | :--- | :--- | :--- |
| **CSRF** | Malicious third-party site triggers state-changing POST | Cryptographic per-session CSRF token + `Sec-Fetch-Site` and `Origin` header validation | **Kernel:** Enforced on 100% of command and action POST endpoints. |
| **XSS** | Injection of malicious scripts into DOM | Automatic context-aware HTML escaping on all text/attributes + strict CSP headers | **Renderer:** Automated in `HTMLRenderer`. |
| **Session Hijacking** | Cookie theft or fixation | HMAC-SHA256 signed session cookies (`HttpOnly`, `SameSite=Lax`, `Secure`) with session rotation | **Session Middleware** |
| **Tenant Spoofing** | Attacker injects `X-Tenant-ID: victim_corp` | Untrusted tenant headers disabled by default; mandatory server-side membership validation | **State Context Pipeline** (ADR-005) |
| **Unbounded DoS** | Malicious client streams gigabytes of form data | Incremental body streaming reading up to `max_form_bytes` (default 1MB, configurable); rejects with 413 | **ASGI Dispatcher** |
| **Path Traversal** | Malicious file upload filename (`../../etc/passwd`) | Server-side sanitization extracting strict base filename, enforcing safe directory resolution | **File Upload Engine** |
| **Replay Attacks** | Replaying captured command mutations | Server-side `IdempotencyBackend` checking action ID and payload fingerprint | **Idempotency Engine** (ADR-001) |

### 2. Content-Security-Policy (CSP) Standards
All HTML page responses served by RADUI include strict security headers:
```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Cache-Control: no-store
```

### 3. Role-Based Access Control (RBAC)
Command and page definitions support declarative authorization:
```python
@app.page("/admin/finance", require_role="finance_admin")
def finance_page(): ...

@app.command("payout.execute", require_permission="payout:write")
def execute_payout(ctx): ...
```
- Unauthorized page visits return HTTP 403 Forbidden with user-friendly error boundaries.
- Unauthorized command invocations return HTTP 403 Forbidden JSON payloads.

## Consequences
- **Positive:** Default-secure architecture: CSRF, XSS, and DoS protections operate automatically without requiring custom developer glue code.
- **Positive:** Verified defense-in-depth preventing tenant spoofing and replay attacks.
- **Trade-off:** Strict CSP policies require all client scripts and stylesheets to originate from the same origin.
