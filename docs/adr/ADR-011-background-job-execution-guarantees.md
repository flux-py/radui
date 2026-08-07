# ADR-011: Background Job Execution Guarantees, Distributed Leasing & Crash Recovery

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
Long-running background operations (e.g. report generation, batch data processing, AI document parsing) cannot execute within the synchronous HTTP request-response cycle without risking gateway timeouts.

However, distributed job execution requires strict lifecycle management:
- If a worker executing a job crashes, the job must not remain stranded in `RUNNING` indefinitely.
- If a worker stalls and its lease is reclaimed, the zombie worker must be prevented from overwriting the status or progress of the new worker.
- Connected browser clients observing the job (`gx.job_panel`) require real-time, low-latency progress telemetry without polling.

## Decision

### 1. Job Lifecycle State Machine

```
[ PENDING ] ------------> [ RUNNING ] ------------> [ COMPLETED ]
      |                         |
      | (cancelled)             | (error or crash)
      v                         v
 [ CANCELLED ]              [ FAILED ]
```

1. `PENDING`: Enqueued in job backend awaiting worker dispatch.
2. `RUNNING`: Claimed by an active worker under an exclusive lease with a monotonic fencing token (`fence_token`).
3. `COMPLETED`: Work finished successfully; result payload persisted.
4. `FAILED`: Unhandled exception or maximum retries exceeded.
5. `CANCELLED`: Explicitly aborted by user or application context via `jobs.cancel(job_id)`.

### 2. Distributed Leasing & Fencing (`RedisJobBackend`)
- Workers claim jobs by acquiring a distributed lease (`claim_job()`) with a configurable TTL (default: 30 seconds) and receiving a monotonic fencing token (`fence_token: int`).
- The executing worker transmits periodic heartbeats (`heartbeat(job_id, fence_token)`).
- When updating progress (`update_progress()`) or completing the job (`mark_completed()`), the backend validates `fence_token`. If another worker has reclaimed the lease due to missed heartbeats, the zombie worker's update is rejected with `StaleLeaseError`.

### 3. Cooperative Cancellation & Hard Timeouts
- Workers periodically inspect cooperative cancellation signals:
  ```python
  def report_task(ctx: gx.JobContext):
      for step in range(100):
          if ctx.is_cancelled():
              return  # Exit gracefully
          ctx.update_progress((step + 1) / 100.0)
  ```
- If a job exceeds its configured hard timeout, the backend marks the job as `FAILED` (timeout error) and revokes its lease.

### 4. Crash Recovery
- During worker startup and background lease scanning, jobs found in `RUNNING` whose lease expiration timestamp has passed without heartbeats are recovered:
  - If retry attempts remain: re-enqueued as `PENDING` with incremented retry count.
  - If retries exhausted: marked as `FAILED` with error `"Worker lease expired (abnormal worker termination)"`.

### 5. Live Telemetry Fanout over SSE
- Progress updates (`ctx.update_progress(fraction, message)`) publish real-time events to connected sessions watching the job ID.
- The `gx.job_panel` component subscribes to these events over the SSE stream, updating progress bars and status indicators in the browser DOM without polling.

## Consequences
- **Positive:** Zero stranded jobs: crashed workers are cleanly detected and jobs recovered via lease expirations.
- **Positive:** Zombie workers are fenced from corrupting job state after lease reclamation.
- **Positive:** Real-time DOM telemetry without client-side polling.
- **Trade-off:** Long-running jobs must include cooperative cancellation checks and heartbeat intervals.
