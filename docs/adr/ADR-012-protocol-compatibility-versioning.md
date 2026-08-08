# ADR-012: Protocol Compatibility, Schema Versioning & Rolling Deployments

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
As an application framework evolves, protocols and persistent schemas change. In production multi-worker environments:
- Rolling deployments result in worker nodes running version $N$ and version $N+1$ concurrently against the same Redis and PostgreSQL databases.
- Browser tabs may remain open across server deployments, running older frontend runtime code while interacting with upgraded backend endpoints.
- Offline mutations stored in client IndexedDB must survive framework upgrades without being corrupted or silently dropped.

## Decision

### 1. Application IR (Intermediate Representation) Versioning
- Component tree definitions and serialized ASTs carry a schema version tag:
  ```json
  {
    "version": 1,
    "app_id": "analytics-portal",
    "pages": [...],
    "components": [...]
  }
  ```
- Backends validate IR version compatibility on ingestion. Backward-compatible changes increment minor revisions; breaking structural changes require explicit migrations.

### 2. Client Mutation Queue & IndexedDB Schema Evolution
- The client storage database `_gx_offline_db` uses explicit integer versioning (`DB_VERSION = 1`).
- Upgrades are performed within standard `onupgradeneeded` lifecycle handlers:
  ```javascript
  req.onupgradeneeded = (e) => {
    const db = e.target.result;
    if (!db.objectStoreNames.contains("mutations")) {
      const store = db.createObjectStore("mutations", { keyPath: "actionId" });
      store.createIndex("timestamp", "timestamp", { unique: false });
      store.createIndex("status", "status", { unique: false });
    }
  };
  ```
- Individual mutation records carry `version: int` (default 1). If a future schema update modifies payload structures, migration transformers convert legacy queued mutations into the new format before dispatch.

### 3. Server-Sent Events (SSE) Protocol Versioning
- SSE streams format events with standardized metadata:
  ```
  id: <monotonic_seq>
  event: <event_type>
  data: {"version": 1, "payload": ...}
  ```
- Unknown event types received by older client runtimes are ignored without breaking the event stream.
- The control event `event: reset` is reserved across all protocol versions to trigger client cache invalidation and page refresh when version incompatibility or buffer pruning occurs.

### 4. Rolling Deployment Backend Compatibility
- Persistent storage schemas (PostgreSQL tables `gx_outbox`, `gx_idempotency`, `gx_events`, `gx_state`) adhere to the **expand-and-contract** migration rule:
  1. New columns are always added as nullable or with backward-compatible defaults.
  2. Workers running version $N$ ignore unrecognized columns.
  3. Workers running version $N+1$ write both old and new representations during rolling transition.
  4. Deprecated columns are removed in a subsequent release after all nodes have transitioned.

### 5. AI Agent Protocols: A2UI & AG-UI Conformance
- A2UI (Agent-to-UI) and AG-UI (Agent-Guided UI) integrations enforce schema validation on all incoming agent tool calls and structured components.
- Agent specifications specify supported protocol versions (e.g. `a2ui_version="1.0"`, `agui_version="1.0"`).
- Tool calls targeting unsupported versions are rejected with structured error responses detailing expected schemas.

## Consequences
- **Positive:** Zero downtime during rolling server upgrades.
- **Positive:** Offline mutations persist safely across client runtime updates.
- **Positive:** Clear evolutionary path for AI agent protocols and event streams.
- **Trade-off:** Requires disciplined adherence to expand-and-contract schema migrations.
