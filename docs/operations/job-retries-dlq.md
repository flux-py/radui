# Runbook: Job Retries and Dead-Letter Queue Investigation

## Symptoms
- `GET /_gx/inspect/runtime` or `GET /_gx/inspect/jobs` shows rising `dlq_depth`, `retry`, `fail`, or `dlq` counters.
- Users report background jobs stuck in `FAILED` status (`TimeoutError` or application exception).

## How to Diagnose
1. Call `GET /_gx/inspect/jobs?limit=25&offset=0` to inspect `queue_depth`, `active_count`, `dlq_depth`, and `dlq_jobs` (`job_id`, `name`, `status`, `attempt`, `max_retries`, `error_type`, `updated_at`).
2. Check worker structured logs (`RedactingJsonFormatter`) around `updated_at` for the failing `job_id` or `error_type`.
3. Check `cluster.jobs.latencies.execution` in `GET /_gx/inspect/runtime` to see if `p95_ms`/`max_ms` is approaching `default_timeout_seconds` (`TimeoutError`).

## Relevant Endpoints and Metrics
- `GET /_gx/inspect/jobs?limit=25&offset=0` (`queue_depth`, `active_count`, `dlq_depth`, `active_jobs`, `dlq_jobs`)
- `GET /_gx/inspect/runtime` (`cluster.jobs.operations`: `enqueue`, `claim`, `complete`, `fail`, `retry`, `dlq`, `stale_recovered`; `cluster.jobs.latencies.execution`)

## Safe Recovery Procedure
1. Identify the root cause from `dlq_jobs[].error_type` and application logs (e.g., transient downstream outage, timeout too low, or invalid input).
2. Fix the underlying defect or increase job timeout if legitimate work exceeds `default_timeout_seconds`.
3. For transient failures where the handler is verified **idempotent**, re-enqueue specific jobs cleanly from an operational script by loading `gx:jobs:job:{job_id}`, resetting `status` to `"queued"` and `attempt` to `0`, removing from `gx:jobs:dlq` (`LREM`), and pushing to `gx:jobs:queue` (`LPUSH`).
4. For permanently invalid jobs, archive the `job_id` metadata and remove it from `gx:jobs:dlq` (`LREM`).

## What NOT to Do
- **Do NOT** bulk-requeue the entire `gx:jobs:dlq` list blindly without verifying handler idempotency and fixing the failing dependency — this causes an immediate retry storm.
- **Do NOT** run `DEL gx:jobs:dlq` without inspecting/archiving dead-lettered job IDs first, as that permanently discards failure visibility.

## Verification After Recovery
1. `GET /_gx/inspect/jobs` shows `dlq_depth` decreasing/stabilized and `queue_depth` draining.
2. `GET /_gx/inspect/runtime` shows `complete` incrementing without new `fail` or `dlq` spikes.

## Known Limitations
- `/_gx/inspect/jobs` intentionally omits `args`, `kwargs`, `result`, and raw `error` strings to prevent secret leakage; full exception tracebacks must be read from application logs.
- `RedisJobBackend` does not include a built-in UI button to replay DLQ items.
