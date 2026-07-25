# ADR-003: High-Watermark SSE Event Replay Architecture, Ordering & Buffer Boundaries

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
Ephemeral message brokers (e.g. Redis Pub/Sub) do not buffer messages during network partitions or client reconnections. If an SSE subscriber disconnects while an event is published, the event is permanently lost, causing client-server DOM state drift.

Conversely, naive polling against a database introduces high latency and server load. An event infrastructure must provide ordered replay across reconnections while defining bounded retention windows and backpressure limits to prevent server memory exhaustion.

## Decision

### 1. Delivery Guarantees & Ordering Scope
- RADUI guarantees **at-least-once, monotonically ordered event delivery within a bounded retention window**.
- **Ordering Scope:** Ordering is guaranteed **per session** (and per tenant/session: `(tenant_id, session_id)`), NOT globally across the entire application cluster.
- Clients MUST perform client-side deduplication against the event sequence (`id: <seq>`).
- Durable storage (`EventBackend`) serves as the authoritative source-of-truth for event sequences and history logs.
- Ephemeral Redis Pub/Sub acts strictly as a low-latency wakeup notification (`NOTIFY`), never as the authoritative delivery payload.

### 2. Atomic Persistence Before Notification
To eliminate races where a subscriber wakes up from a notification and queries storage before the event has been written:
1. The publisher appends the event to authoritative durable storage (`EventBackend.append()`) and captures the allocated sequence number.
2. Only after durable storage commit succeeds does the publisher broadcast a lightweight wakeup notification over Redis Pub/Sub.

### 3. High-Watermark Replay Protocol
When a client connects or reconnects to `/_gx/events`:
1. The client supplies its last acknowledged cursor via `Last-Event-ID` or `?since=<seq>`.
2. The broker registers the client's bounded in-memory queue (`subscriber_queue_size = 64`) to capture concurrent live events.
3. The broker queries authoritative storage for current high-watermark (`HWM`).
4. **Replay Drain Phase:** Historical events from `(last_event_id ... HWM]` are read in paginated batches (`limit=1000`) and streamed to the client.
5. **Live Transition Phase:** Once caught up to `HWM`, the stream smoothly drains the live queue, skipping any event with `sequence <= delivered_sequence`.

### 4. Client Acknowledgment vs Application-State Application
- `Last-Event-ID` indicates network delivery receipt at the browser's `EventSource`.
- If an asynchronous DOM patch application fails in browser runtime, the client does NOT advance its cursor, and dispatches a refresh request (`/_gx/refresh`) or triggers a reload to re-synchronize state.

### 5. Backpressure & Bounded Queue Shedding
- Each subscriber connection is allocated a bounded queue (`subscriber_queue_size: int = 64`).
- If a slow client fails to drain events and the queue overflows (`asyncio.QueueFull`), the broker proactively clears the stalled queue before enqueueing an `event: reset` control message:
  ```python
  while not target.empty():
      try:
          target.get_nowait()
      except asyncio.QueueEmpty:
          break
  target.put_nowait(EventRecord(rec.sequence, "reset", {}))
  ```
- This guarantees the reset message is delivered without raising `QueueFull` and prevents slow browser tabs from exhausting server memory.

## Consequences
- **Positive:** Ordered, gap-free state synchronization across network disconnections within the retention window.
- **Positive:** Strict per-(tenant, session) ordering avoids cluster-wide serialization bottlenecks.
- **Positive:** Bounded memory utilization on servers via strict queue sizing and proactive reset shedding.
- **Boundaries:** Does not guarantee infinite history retention; clients disconnected beyond the retention window receive `event: reset`.
- **Trade-off:** Applications must store session event streams in persistent backends (`SQLiteEventBackend`, `RedisEventBackend`, `PostgreSQLEventBackend`).
