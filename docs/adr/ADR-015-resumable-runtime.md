# ADR-015: Resumable Application Runtime (M2.0)

- **Status:** Accepted (M2.0)
- **Context:** Full-page client hydration scales poorly with component count. RadUI already serializes declarative interaction descriptors (`M1.8`), allowing state and descriptors to be resumed lazily per boundary.
- **Decision:** Introduce `radui/resumability/` (`ResumableBoundarySnapshot`, `ExecutionDescriptor`, `StateMigrationRegistry`, `restore_boundary`) and `window.RadUIResumability` in `CLIENT_JS` with `resumable=True` on `Component` and server verification at `POST /_gx/resume`.
- **Consequences:** Lazy resumable boundaries incur zero eager initialization on page load (`activatedCount == 0`) and activate individually in `<10 ms` on first interaction while enforcing `auth_scope` and CSRF boundaries.
