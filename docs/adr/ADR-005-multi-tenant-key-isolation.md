# ADR-005: Multi-Tenant Logical Namespace Isolation & Database Row-Level Security Enforcement

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
Multi-tenant applications require strict isolation between organizational tenants. If storage keys, query caches, or event streams share flat namespaces, inadvertent key collisions or cross-tenant data leaks can occur.

Furthermore, client-supplied HTTP headers (e.g. `X-Tenant-ID`) are attacker-controlled. Trusting client headers directly without authenticating the caller and verifying tenant membership creates a critical authorization bypass vulnerability.

At the database level, relying solely on `WHERE tenant_id = :id` clauses in application queries is error-prone. A single missed `WHERE` clause can leak or corrupt data across tenants. Conversely, naive Row-Level Security (RLS) policies that omit `WITH CHECK`, table ownership enforcement, or connection-pool context cleanup leave security holes.

## Decision

### 1. Logical Namespace Partitioning
- RADUI provides **logical namespace isolation**, NOT cryptographic isolation. Key prefixing partitions state keys within shared storage backends.
- Every state storage key is automatically prefixed with `tenant_id` across all scopes:
  - App Scope: `gx:state:<tenant_id>:app:global`
  - User Scope: `gx:state:<tenant_id>:user:<user_id>`
  - Session Scope: `gx:state:<tenant_id>:session:<session_id>`
  - View Scope: `gx:state:<tenant_id>:view:<view_id>`
- SWR query caching (`gx.query`, `gx.aquery`, `gx.invalidate_query`) partitions cache entries using `f"{tenant_id}:{key}"`.
- Event streams partition Redis channels and database logs by `(tenant_id, session_id)`.

### 2. Trusted Tenant Verification Pipeline
RADUI enforces a 5-step pipeline for establishing tenant context:

```
[ Request Ingestion ]
         |
         v
[ 1. Authenticate Identity ] --------> Extract trusted user_id from signed session / JWT / mTLS
         |
         v
[ 2. Resolve Tenant ] ---------------> Execute tenant_id_resolver(request) from trusted claims
         |
         v
[ 3. Validate Membership ] ----------> Verify user_id has authorized membership in candidate tenant
         |
         v
[ 4. Construct Context ] ------------> Create immutable StateContext(user_id=..., tenant_id=...)
         |
         v
[ 5. Propagate ] --------------------> Bind tenant_id to all state keys, query cache, outbox & events
```

### 3. Untrusted Header Protection
- Direct ingestion of raw client headers (`X-Tenant-ID`, `Tenant-ID`) is disabled by default (`allow_untrusted_tenant_headers = False`).
- In production deployments, ingress reverse proxies MUST strip all client-supplied tenant headers.
- If an unverified client passes a tenant header without authorization, the request is immediately rejected with HTTP 403 Forbidden.
- Applications behind trusted enterprise gateways (where the gateway strips external headers and injects cryptographic identity tokens) configure a `tenant_membership_validator: Callable[[Request, str | None, str | None], bool]` that validates access before adopting the tenant context.

### 4. Database-Level Enforcement: Hardened PostgreSQL Row-Level Security (RLS)
For applications requiring kernel-level database isolation, RADUI specifies the following hardened RLS configuration:

#### A. Policy Definition with Mandatory `WITH CHECK`
Both read (`USING`) and write (`WITH CHECK`) boundaries are strictly enforced:
```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY; -- Enforce even for table owner

CREATE POLICY tenant_isolation_policy ON orders
FOR ALL
USING (tenant_id = current_setting('app.current_tenant', false))
WITH CHECK (tenant_id = current_setting('app.current_tenant', false));
```
- Passing `false` as the second argument to `current_setting('app.current_tenant', false)` causes PostgreSQL to raise a hard runtime error if the setting has not been set, failing closed rather than returning null.

#### B. Privilege Separation & Role Hardening
- Application database users MUST NOT own the application tables and MUST NOT possess `SUPERUSER` or `BYPASSRLS` privileges.
- Tables are owned by a dedicated migration role (`RADUI_migration`), while runtime workers connect as `RADUI_app`.

#### C. Transaction-Local Scope & Pool Context Cleanup
- Tenant context MUST be established using `SET LOCAL` within an explicit transaction:
  ```sql
  BEGIN;
  SELECT set_config('app.current_tenant', :tenant_id, true); -- local to transaction
  -- Execute business queries here
  COMMIT;
  ```
- When using connection pools (`psycopg_pool`), connection wrappers execute `RESET ALL;` or `DISCARD ALL;` upon returning the connection to the pool, preventing leaked tenant context into subsequent pooled operations.

## Consequences
- **Positive:** Dual-layer tenant isolation: application namespace partitioning combined with database kernel-level RLS.
- **Positive:** Fails closed if tenant context is uninitialized (`current_setting(..., false)`).
- **Positive:** Protection against tenant spoofing via mandatory membership validation.
- **Boundaries:** Key prefixing provides logical partitioning. Applications requiring strict cryptographic separation should employ per-tenant database schemas or encryption keys.
- **Trade-off:** RLS policies require all pooled database queries to execute within transaction blocks that initialize `app.current_tenant`.
