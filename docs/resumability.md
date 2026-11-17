# RadUI Resumable Application Runtime (M2.0)

RadUI M2.0 adds Qwik-inspired resumability on top of the existing M1.8 interaction engine and M1.9 SPA navigation without requiring client-side full-tree hydration.

## 1. Architecture & Protocol

- **Opt-In Boundaries (`resumable=True`):** Any component builder accepts `resumable=True` and `resumable_activation="lazy"|"visible"|"eager"|"interaction"`.
- **Serialized Snapshots (`#gx-resumable-state`):** `collect_resumable_boundaries()` extracts `ResumableBoundarySnapshot` records (`schema_version="1.0"`, `ExecutionDescriptor`, `local_state`, `scoped_state`, `bind_local`, `deps`, and `auth_scope` digest).
- **Security:** Rejects secrets (`password`, `token`, `api_key`, `secret`, etc.) and prototype-pollution keys (`__proto__`, `constructor`, `prototype`). `POST /_gx/resume` validates CSRF, route ownership, and `auth_scope` (`session_id:user_id:tenant_id`).
- **Schema Migration:** `StateMigrationRegistry` supports explicit version-to-version state upgrades.

## 2. Browser Lazy Activation (`window.RadUIResumability`)

- On initial SSR load, `[data-gx-resumable="lazy"]` boundaries perform **zero** eager hydration (`activatedCount === 0`).
- On the first delegated interaction inside a resumable boundary, `resumeBoundary(el)` hydrates only that boundary's `WeakMap` state and `bind_local` targets (`data-gx-resumed="1"`).
