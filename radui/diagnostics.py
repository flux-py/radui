from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html as html_lib
import threading
import time
from typing import Any

from radui.core.config import redact_secrets
from radui.observability import collect_cluster_snapshot

MAX_WORKERS_RETURNED = 100
MAX_SSE_GROUPS = 20
DEFAULT_JOB_PAGE_LIMIT = 25
MAX_JOB_PAGE_LIMIT = 100


def _parse_iso_age_seconds(ts: str | None, now: datetime) -> float | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, round((now - dt).total_seconds(), 2))
    except Exception:
        return None


def _hash_identifier(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


class DiagnosticsCollector:
    """Bounded, TTL-cached runtime diagnostics collector for /_gx/inspect/*."""

    def __init__(self, *, cache_ttl_seconds: float = 1.0) -> None:
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        if self.cache_ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and (now - entry[0]) < self.cache_ttl_seconds:
                return entry[1]
        return None

    def _set_cached(self, key: str, value: dict[str, Any]) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        with self._lock:
            self._cache[key] = (time.monotonic(), value)

    @staticmethod
    def _redis_client(app: Any) -> Any | None:
        for obj in (app.events.backend, app.state_runtime.backend, app.jobs):
            cli = getattr(obj, "_client", None) or getattr(obj, "_redis_client", None)
            if cli is not None:
                return cli
        return None

    def _probe_redis(self, app: Any) -> dict[str, Any]:
        configured = app.config.backend == "redis"
        if not configured:
            return {"configured": False, "connected": None, "ping_ms": None, "error": None}
        client = self._redis_client(app)
        if client is None:
            return {
                "configured": True,
                "connected": False,
                "ping_ms": None,
                "error": "Redis client unavailable",
            }
        t0 = time.perf_counter()
        try:
            ok = bool(client.ping())
            ping_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return {
                "configured": True,
                "connected": ok,
                "ping_ms": ping_ms,
                "error": None if ok else "Redis ping returned false",
            }
        except Exception as exc:
            return {
                "configured": True,
                "connected": False,
                "ping_ms": None,
                "error": f"Redis ping failed: {type(exc).__name__}",
            }

    def runtime_diagnostics(self, app: Any) -> dict[str, Any]:
        cached = self._get_cached("runtime")
        if cached is not None:
            return cached

        now = datetime.now(timezone.utc)
        local_subsystems = app._collect_worker_observability()
        local_ident = app.worker_identity.to_dict()
        local_uptime = _parse_iso_age_seconds(local_ident.get("started_at"), now)
        redis_info = self._probe_redis(app)
        warnings: list[str] = []

        if app.config.backend == "redis":
            client = self._redis_client(app) if redis_info.get("connected") else None
            cluster_raw = collect_cluster_snapshot(
                client,
                prefix=app.observability.prefix,
                max_workers=MAX_WORKERS_RETURNED,
            )
            available = bool(cluster_raw.get("available", False))
            if not redis_info.get("connected"):
                warnings.append("Redis backend unreachable")
            malformed = int(cluster_raw.get("malformed_snapshots", 0) or 0)
            if malformed > 0:
                warnings.append(f"{malformed} malformed worker snapshot(s) ignored")

            # Build bounded worker roster with age and stale detection
            stale_threshold_s = max(5.0, float(app.config.sse_heartbeat_interval_seconds) * 2.5)
            workers_out: list[dict[str, Any]] = []
            stale_count = 0
            raw_workers = []
            if available and client is not None:
                # Re-use full snapshots only when available; collect_cluster_snapshot returns worker dicts
                # Query worker keys bounded to MAX_WORKERS_RETURNED for timestamp + active SSE
                import json

                try:
                    keys = []
                    for k in client.scan_iter(match=f"{app.observability.prefix}*", count=200):
                        keys.append(k)
                        if len(keys) >= MAX_WORKERS_RETURNED:
                            break
                    if keys:
                        for raw_val in client.mget(keys):
                            if not raw_val:
                                continue
                            try:
                                if isinstance(raw_val, bytes):
                                    raw_val = raw_val.decode("utf-8")
                                parsed = json.loads(raw_val)
                                if isinstance(parsed, dict) and "worker" in parsed and "subsystems" in parsed:
                                    raw_workers.append(parsed)
                            except Exception:
                                continue
                except Exception:
                    pass

            for snap in raw_workers[:MAX_WORKERS_RETURNED]:
                w = snap.get("worker", {})
                snap_ts = snap.get("timestamp")
                hb_age = _parse_iso_age_seconds(snap_ts, now)
                uptime_s = _parse_iso_age_seconds(w.get("started_at"), now)
                is_stale = hb_age is not None and hb_age > stale_threshold_s
                if is_stale:
                    stale_count += 1
                sse_sub = snap.get("subsystems", {}).get("sse", {})
                workers_out.append(
                    {
                        "worker_id": str(w.get("worker_id", "")),
                        "hostname": str(w.get("hostname", "")),
                        "pid": w.get("pid"),
                        "environment": str(w.get("environment", "")),
                        "backend_mode": str(w.get("backend_mode", "")),
                        "started_at": w.get("started_at"),
                        "uptime_seconds": uptime_s,
                        "snapshot_timestamp": snap_ts,
                        "snapshot_age_seconds": hb_age,
                        "heartbeat_status": "stale" if is_stale else "healthy",
                        "active_sse_connections": int(sse_sub.get("active_connections", 0) or 0),
                    }
                )

            if available and len(workers_out) == 0:
                warnings.append("Zero active workers registered in Redis cluster")
            if stale_count > 0:
                warnings.append(f"{stale_count} stale worker snapshot(s) detected")

            agg = cluster_raw.get("aggregated", {}) if available else {}
            state_data = dict(agg.get("state", {})) if available else {"operations": None, "latencies": None}
            state_data["ttl_expirations"] = {
                "available": False,
                "note": "Actual Redis TTL expiration counts are not currently available without keyspace notifications.",
            }
            events_data = dict(agg.get("events", {})) if available else {"operations": None, "latencies": None}
            sse_data = dict(agg.get("sse", {})) if available else {"operations": None, "latencies": None}
            jobs_data = dict(agg.get("jobs", {})) if available else {"operations": None, "queue_depth": None, "active_count": None, "dlq_depth": None, "latencies": None}

            if not redis_info.get("connected") or not available:
                overall_status = "unavailable"
            elif warnings or app._shutting_down or not app._ready:
                overall_status = "degraded"
            else:
                overall_status = "healthy"

            cluster_block = {
                "scope": "cluster",
                "available": available,
                "active_workers": len(workers_out),
                "stale_workers": stale_count,
                "malformed_snapshots": malformed,
                "workers": workers_out,
                "sse_governance": sse_data,
                "state": state_data,
                "events": events_data,
                "jobs": jobs_data,
            }
        else:
            # Local (memory / sqlite) single-process diagnostics
            state_local = dict(local_subsystems.get("state", {}))
            state_local["ttl_expirations"] = {
                "available": False,
                "note": "Actual TTL expiration counts are not currently tracked for this backend.",
            }
            if app._shutting_down or not app._ready:
                overall_status = "degraded"
                warnings.append("Application is not ready or is shutting down")
            else:
                overall_status = "healthy"
            cluster_block = {
                "scope": "local",
                "available": True,
                "active_workers": 1,
                "stale_workers": 0,
                "malformed_snapshots": 0,
                "workers": [
                    {
                        **local_ident,
                        "uptime_seconds": local_uptime,
                        "snapshot_timestamp": now.isoformat(),
                        "snapshot_age_seconds": 0.0,
                        "heartbeat_status": "healthy",
                        "active_sse_connections": int(local_subsystems.get("sse", {}).get("active_connections", 0) or 0),
                    }
                ],
                "sse_governance": local_subsystems.get("sse", {}),
                "state": state_local,
                "events": local_subsystems.get("events", {}),
                "jobs": local_subsystems.get("jobs", {}),
            }

        payload = redact_secrets(
            {
                "ok": True,
                "timestamp": now.isoformat(),
                "status": overall_status,
                "warnings": warnings,
                "local_worker": {
                    "worker": local_ident,
                    "uptime_seconds": local_uptime,
                    "subsystems": local_subsystems,
                },
                "redis": redis_info,
                "cluster": cluster_block,
            }
        )
        self._set_cached("runtime", payload)
        return payload

    def job_diagnostics(self, app: Any, *, limit: int = DEFAULT_JOB_PAGE_LIMIT, offset: int = 0) -> dict[str, Any]:
        eff_limit = max(1, min(int(limit), MAX_JOB_PAGE_LIMIT))
        eff_offset = max(0, int(offset))
        cache_key = f"jobs:{eff_limit}:{eff_offset}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        jobs_backend = app.jobs
        is_redis = hasattr(jobs_backend, "_redis_client") and hasattr(jobs_backend, "prefix")
        if is_redis:
            client = getattr(jobs_backend, "_redis_client", None)
            prefix = getattr(jobs_backend, "prefix", "gx:jobs:")
            if client is None:
                payload = {
                    "ok": True,
                    "available": False,
                    "backend": "redis",
                    "queue_depth": None,
                    "active_count": None,
                    "dlq_depth": None,
                    "pagination": {"limit": eff_limit, "offset": eff_offset, "active_total": 0, "dlq_total": 0},
                    "active_jobs": [],
                    "dlq_jobs": [],
                }
                self._set_cached(cache_key, payload)
                return payload
            try:
                queue_depth = int(client.llen(f"{prefix}queue"))
                active_ids = sorted(str(x) for x in client.smembers(f"{prefix}active"))
                dlq_total = int(client.llen(f"{prefix}dlq"))
                dlq_ids = [
                    str(x) for x in client.lrange(f"{prefix}dlq", eff_offset, eff_offset + eff_limit - 1)
                ]
                active_slice = active_ids[eff_offset : eff_offset + eff_limit]

                active_jobs: list[dict[str, Any]] = []
                for jid in active_slice:
                    rec = jobs_backend._load_job(jid) or {}
                    owner = client.get(f"{prefix}lock:{jid}")
                    ttl_raw = client.ttl(f"{prefix}lock:{jid}")
                    lease_rem = int(ttl_raw) if isinstance(ttl_raw, int) and ttl_raw >= 0 else None
                    active_jobs.append(
                        {
                            "job_id": jid,
                            "name": str(rec.get("name", "unknown")),
                            "status": str(rec.get("status", "unknown")),
                            "attempt": int(rec.get("attempt", 0) or 0),
                            "max_retries": int(rec.get("max_retries", 0) or 0),
                            "owner_worker_id": str(owner) if owner else None,
                            "lease_remaining_seconds": lease_rem,
                            "updated_at": rec.get("updated_at"),
                        }
                    )

                dlq_jobs: list[dict[str, Any]] = []
                for jid in dlq_ids:
                    rec = jobs_backend._load_job(jid) or {}
                    dlq_jobs.append(
                        {
                            "job_id": jid,
                            "name": str(rec.get("name", "unknown")),
                            "status": str(rec.get("status", "failed")),
                            "attempt": int(rec.get("attempt", 0) or 0),
                            "max_retries": int(rec.get("max_retries", 0) or 0),
                            "error_type": rec.get("error_type"),
                            "updated_at": rec.get("updated_at"),
                        }
                    )

                payload = {
                    "ok": True,
                    "available": True,
                    "backend": "redis",
                    "queue_depth": queue_depth,
                    "active_count": len(active_ids),
                    "dlq_depth": dlq_total,
                    "pagination": {
                        "limit": eff_limit,
                        "offset": eff_offset,
                        "active_total": len(active_ids),
                        "dlq_total": dlq_total,
                    },
                    "active_jobs": active_jobs,
                    "dlq_jobs": dlq_jobs,
                }
                self._set_cached(cache_key, payload)
                return payload
            except Exception:
                payload = {
                    "ok": True,
                    "available": False,
                    "backend": "redis",
                    "queue_depth": None,
                    "active_count": None,
                    "dlq_depth": None,
                    "pagination": {"limit": eff_limit, "offset": eff_offset, "active_total": 0, "dlq_total": 0},
                    "active_jobs": [],
                    "dlq_jobs": [],
                }
                self._set_cached(cache_key, payload)
                return payload

        # Local or SQLite job backend
        backend_name = "sqlite" if app.config.backend == "sqlite" else "local"
        local_jobs = getattr(jobs_backend, "_latest", None) or getattr(jobs_backend, "_jobs", None)
        if isinstance(local_jobs, dict):
            all_snaps = list(local_jobs.values())
            queued = [s for s in all_snaps if getattr(s.status, "value", str(s.status)) == "queued"]
            running = [s for s in all_snaps if getattr(s.status, "value", str(s.status)) == "running"]
            failed = [s for s in all_snaps if getattr(s.status, "value", str(s.status)) == "failed"]
            active_slice = running[eff_offset : eff_offset + eff_limit]
            dlq_slice = failed[eff_offset : eff_offset + eff_limit]
            payload = {
                "ok": True,
                "available": True,
                "backend": backend_name,
                "queue_depth": len(queued),
                "active_count": len(running),
                "dlq_depth": len(failed),
                "pagination": {
                    "limit": eff_limit,
                    "offset": eff_offset,
                    "active_total": len(running),
                    "dlq_total": len(failed),
                },
                "active_jobs": [
                    {
                        "job_id": s.id,
                        "name": s.name,
                        "status": getattr(s.status, "value", str(s.status)),
                        "attempt": getattr(s, "attempt", 1),
                        "max_retries": 0,
                        "owner_worker_id": app.worker_id,
                        "lease_remaining_seconds": None,
                        "updated_at": getattr(s, "updated_at", None),
                    }
                    for s in active_slice
                ],
                "dlq_jobs": [
                    {
                        "job_id": s.id,
                        "name": s.name,
                        "status": getattr(s.status, "value", str(s.status)),
                        "attempt": getattr(s, "attempt", 1),
                        "max_retries": 0,
                        "error_type": getattr(s, "error_type", None),
                        "updated_at": getattr(s, "updated_at", None),
                    }
                    for s in dlq_slice
                ],
            }
        else:
            payload = {
                "ok": True,
                "available": True,
                "backend": backend_name,
                "queue_depth": 0,
                "active_count": 0,
                "dlq_depth": 0,
                "pagination": {"limit": eff_limit, "offset": eff_offset, "active_total": 0, "dlq_total": 0},
                "active_jobs": [],
                "dlq_jobs": [],
            }
        self._set_cached(cache_key, payload)
        return payload

    def sse_diagnostics(self, app: Any) -> dict[str, Any]:
        broker = app.events
        base_metrics = broker.metrics()
        gov = broker.governance
        gov_snap = (
            gov.observability_snapshot()
            if hasattr(gov, "observability_snapshot")
            else broker.governance_metrics()
        )

        # Bounded, hashed session subscriber groups (never raw session IDs or IPs)
        with broker._lock:
            groups = sorted(
                (
                    {"session_hash": _hash_identifier(sid), "subscribers": len(subs)}
                    for sid, subs in broker._subscribers.items()
                    if subs
                ),
                key=lambda g: g["subscribers"],
                reverse=True,
            )[:MAX_SSE_GROUPS]

        is_redis_gov = gov_snap.get("mode") == "redis"
        gov_available = True
        if is_redis_gov:
            get_cli = getattr(gov, "_get_client", None)
            gov_available = (get_cli() is not None) if callable(get_cli) else False

        return {
            "ok": True,
            "metrics": base_metrics,
            "local": {
                "worker_id": broker.worker_id,
                "active_connections": base_metrics["active_connections"],
                "active_subscribers": base_metrics["active_subscribers"],
                "session_groups": groups,
            },
            "governance": {
                "mode": gov_snap.get("mode", "memory"),
                "available": gov_available,
                "fail_open": bool(getattr(gov, "fail_open", False)),
                "lease_ttl_seconds": float(getattr(gov, "lease_ttl_seconds", app.config.sse_lease_ttl_seconds)),
                "max_connections_per_session": broker.max_connections_per_session,
                "max_connections_per_ip": broker.max_connections_per_ip,
                "rate_limit": broker.connect_rate_limit,
                "rate_window_seconds": broker.connect_rate_window_seconds,
                "operations": gov_snap.get("operations", {}),
                "latencies": gov_snap.get("latencies", {}),
            },
        }


def _fmt_ms(val: Any) -> str:
    if val is None:
        return "unavailable"
    return f"{float(val):.2f} ms"


def render_inspector_dashboard_html(
    *,
    app_id: str,
    page_count: int,
    command_count: int,
    job_count: int,
    total_traces: int,
    runtime_data: dict[str, Any],
    jobs_data: dict[str, Any],
    sse_data: dict[str, Any],
    traces_rows_html: str,
    dag_svg: str,
) -> str:
    status = str(runtime_data.get("status", "unknown"))
    status_label = html_lib.escape(status.upper())
    warnings = runtime_data.get("warnings") or []
    warnings_html = "".join(f"<li>{html_lib.escape(str(w))}</li>" for w in warnings)
    warnings_block = (
        f"<div id='gx-warnings-box' class='warn-box'><strong>Degradation Warnings:</strong><ul>{warnings_html}</ul></div>"
        if warnings
        else "<div id='gx-warnings-box' class='warn-box' style='display:none'></div>"
    )

    redis_info = runtime_data.get("redis", {})
    if not redis_info.get("configured"):
        redis_label = "Local Mode"
    elif redis_info.get("connected"):
        redis_label = f"Connected ({redis_info.get('ping_ms', 0)} ms)"
    else:
        redis_label = "Unavailable"

    cluster = runtime_data.get("cluster", {})
    workers = cluster.get("workers") or []
    worker_rows = "".join(
        f"<tr>"
        f"<td>{html_lib.escape(str(w.get('worker_id', '')))}</td>"
        f"<td>{html_lib.escape(str(w.get('hostname', '')))} ({html_lib.escape(str(w.get('pid', '')))})</td>"
        f"<td>{html_lib.escape(str(w.get('backend_mode', '')))}</td>"
        f"<td>{html_lib.escape(str(w.get('uptime_seconds', 'n/a')))}s</td>"
        f"<td>{html_lib.escape(str(w.get('snapshot_age_seconds', 'n/a')))}s</td>"
        f"<td><span class='badge badge-{html_lib.escape(str(w.get('heartbeat_status', 'stale')))}'>{html_lib.escape(str(w.get('heartbeat_status', '')))}</span></td>"
        f"<td>{int(w.get('active_sse_connections', 0) or 0)}</td>"
        f"</tr>"
        for w in workers
    ) or "<tr><td colspan='7'>No active workers registered</td></tr>"

    gov_ops = (sse_data.get("governance") or {}).get("operations") or {}
    state_lat = ((cluster.get("state") or {}).get("latencies") or {})
    event_lat = ((cluster.get("events") or {}).get("latencies") or {})
    latency_rows = ""
    for label, entry in (
        ("State get", state_lat.get("get")),
        ("State set", state_lat.get("set")),
        ("State CAS", state_lat.get("cas")),
        ("State delete", state_lat.get("delete")),
        ("Event publish", event_lat.get("publish")),
        ("Event replay", event_lat.get("replay")),
    ):
        if isinstance(entry, dict):
            latency_rows += (
                f"<tr><td>{label}</td><td>{int(entry.get('count', 0) or 0)}</td>"
                f"<td>{int(entry.get('errors', 0) or 0)}</td>"
                f"<td>{_fmt_ms(entry.get('p50_ms'))}</td>"
                f"<td>{_fmt_ms(entry.get('p95_ms'))}</td>"
                f"<td>{_fmt_ms(entry.get('max_ms'))}</td></tr>"
            )
        else:
            latency_rows += f"<tr><td>{label}</td><td colspan='5'>unavailable</td></tr>"

    active_jobs = jobs_data.get("active_jobs") or []
    dlq_jobs = jobs_data.get("dlq_jobs") or []
    job_rows = "".join(
        f"<tr><td>{html_lib.escape(str(j.get('job_id', '')))}</td>"
        f"<td>{html_lib.escape(str(j.get('name', '')))}</td>"
        f"<td>{html_lib.escape(str(j.get('status', '')))}</td>"
        f"<td>{html_lib.escape(str(j.get('owner_worker_id') or '-'))}</td>"
        f"<td>{html_lib.escape(str(j.get('lease_remaining_seconds') if j.get('lease_remaining_seconds') is not None else '-'))}</td>"
        f"<td>{int(j.get('attempt', 0) or 0)}/{int(j.get('max_retries', 0) or 0)}</td></tr>"
        for j in active_jobs
    ) or "<tr><td colspan='6'>No active jobs</td></tr>"

    dlq_rows = "".join(
        f"<tr><td>{html_lib.escape(str(j.get('job_id', '')))}</td>"
        f"<td>{html_lib.escape(str(j.get('name', '')))}</td>"
        f"<td>{html_lib.escape(str(j.get('error_type') or 'unknown'))}</td>"
        f"<td>{int(j.get('attempt', 0) or 0)}</td></tr>"
        for j in dlq_jobs
    ) or "<tr><td colspan='4'>DLQ empty</td></tr>"

    ts = html_lib.escape(str(runtime_data.get("timestamp", "")))
    q_depth = jobs_data.get("queue_depth") if jobs_data.get("queue_depth") is not None else "unavailable"
    a_depth = jobs_data.get("active_count") if jobs_data.get("active_count") is not None else "unavailable"
    d_depth = jobs_data.get("dlq_depth") if jobs_data.get("dlq_depth") is not None else "unavailable"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RADUI Runtime Inspector</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 24px; margin: 0; }}
.wrap {{ max-width: 1240px; margin: 0 auto; }}
.topbar {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; margin-bottom:20px; }}
.controls {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; font-size:13px; }}
button, select {{ background:#1e293b; color:#f8fafc; border:1px solid #334155; border-radius:6px; padding:6px 12px; cursor:pointer; font-size:13px; }}
button:hover {{ background:#334155; }}
.stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 20px; }}
.stat-card {{ background: #111827; border-radius: 8px; padding: 14px; border: 1px solid #1e293b; }}
.stat-label {{ font-size: 12px; color: #94a3b8; }}
.stat-value {{ font-size: 20px; font-weight: 700; color: #38bdf8; margin-top: 4px; }}
.badge {{ padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
.badge-healthy {{ background: #14532d; color: #86efac; }}
.badge-degraded {{ background: #78350f; color: #fde68a; }}
.badge-unavailable, .badge-stale {{ background: #7f1d1d; color: #fca5a5; }}
.warn-box {{ background:#451a03; border:1px solid #92400e; color:#fde68a; padding:12px 16px; border-radius:8px; margin-bottom:20px; font-size:13px; }}
.section {{ margin-bottom: 24px; }}
.section h2 {{ font-size: 16px; margin: 0 0 10px 0; }}
.table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #1e293b; }}
table {{ width: 100%; border-collapse: collapse; font-family: ui-monospace, monospace; font-size: 13px; background: #111827; }}
th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid #1e293b; }}
th {{ background: #1f2937; color: #94a3b8; font-weight: 600; }}
.cat-badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
.cat-render {{ background: #1e3a8a; color: #93c5fd; }}
.cat-command {{ background: #14532d; color: #86efac; }}
.cat-state {{ background: #701a75; color: #f0abfc; }}
.cat-job {{ background: #78350f; color: #fde68a; }}
.cat-error {{ background: #7f1d1d; color: #fca5a5; }}
.muted {{ color:#94a3b8; font-size:12px; }}
</style></head><body>
<div class="wrap">
<div class="topbar">
  <div>
    <h1 style="margin:0; font-size:22px;">RADUI Runtime Inspector <span id="gx-status-badge" class="badge badge-{html_lib.escape(status)}">{status_label}</span></h1>
    <p class="muted" style="margin:4px 0 0 0;">App: {html_lib.escape(app_id)} &bull; Last refresh: <span id="gx-last-refresh">{ts}</span></p>
  </div>
  <div class="controls">
    <button type="button" id="gx-refresh-btn" aria-label="Refresh diagnostics now">Refresh Now</button>
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
      <input type="checkbox" id="gx-autorefresh-toggle" aria-label="Toggle auto-refresh"> Auto-refresh
    </label>
    <select id="gx-autorefresh-interval" aria-label="Auto-refresh interval">
      <option value="5000">5s</option>
      <option value="10000" selected>10s</option>
      <option value="30000">30s</option>
    </select>
    <a href="/_gx/inspect/dag" target="_blank" style="color:#a855f7; text-decoration:none; font-weight:600;">Raw SVG DAG ↗</a>
    <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:600;">← Back to App</a>
  </div>
</div>

{warnings_block}

<div class="stat-grid">
  <div class="stat-card"><div class="stat-label">Application ID</div><div class="stat-value" style="font-size:16px">{html_lib.escape(app_id)}</div></div>
  <div class="stat-card"><div class="stat-label">Redis Health</div><div class="stat-value" id="gx-redis-health" style="font-size:16px">{html_lib.escape(redis_label)}</div></div>
  <div class="stat-card"><div class="stat-label">Active Workers</div><div class="stat-value" id="gx-active-workers">{int(cluster.get('active_workers', 0) or 0)}</div></div>
  <div class="stat-card"><div class="stat-label">Local / Global SSE</div><div class="stat-value" id="gx-sse-active">{int(sse_data['metrics']['active_connections'])}</div></div>
  <div class="stat-card"><div class="stat-label">Jobs (Q / A / DLQ)</div><div class="stat-value" id="gx-jobs-depth" style="font-size:16px">{html_lib.escape(f"{q_depth} / {a_depth} / {d_depth}")}</div></div>
  <div class="stat-card"><div class="stat-label">Total Traces</div><div class="stat-value">{total_traces}</div></div>
  <div class="stat-card"><div class="stat-label">Pages / Cmds / Jobs</div><div class="stat-value" style="font-size:16px">{page_count} / {command_count} / {job_count}</div></div>
</div>

<div class="section">
  <h2>Worker Roster</h2>
  <div class="table-wrap"><table><thead><tr><th>Worker ID</th><th>Host (PID)</th><th>Backend</th><th>Uptime</th><th>Heartbeat Age</th><th>Status</th><th>Active SSE</th></tr></thead><tbody id="gx-workers-body">{worker_rows}</tbody></table></div>
</div>

<div class="section">
  <h2>SSE Governance &amp; Rejections</h2>
  <div class="table-wrap"><table><thead><tr><th>Mode</th><th>Admitted</th><th>Rate-Limit Rej</th><th>Session-Limit Rej</th><th>IP-Limit Rej</th><th>Leases Renewed</th><th>Expired Leases</th><th>Renewal Failures</th></tr></thead><tbody id="gx-sse-body"><tr><td>{html_lib.escape(str((sse_data.get('governance') or {}).get('mode', 'memory')))}</td><td>{int(gov_ops.get('admitted', 0) or 0)}</td><td>{int(gov_ops.get('rejected_rate_limit', 0) or 0)}</td><td>{int(gov_ops.get('rejected_session_limit', 0) or 0)}</td><td>{int(gov_ops.get('rejected_ip_limit', 0) or 0)}</td><td>{int(gov_ops.get('leases_renewed', 0) or 0)}</td><td>{int(gov_ops.get('expired_leases', 0) or 0)}</td><td>{int(gov_ops.get('renewal_failures', 0) or 0)}</td></tr></tbody></table></div>
</div>

<div class="section">
  <h2>State &amp; Event Latency (Cluster Histogram Aggregation)</h2>
  <p class="muted" style="margin:0 0 8px 0;">State TTL expirations: unavailable (actual Redis TTL expiration counts are not currently available without keyspace notifications).</p>
  <div class="table-wrap"><table><thead><tr><th>Operation</th><th>Count</th><th>Errors</th><th>p50</th><th>p95</th><th>Max</th></tr></thead><tbody id="gx-latency-body">{latency_rows}</tbody></table></div>
</div>

<div class="section">
  <h2>Active Jobs &amp; DLQ</h2>
  <div class="table-wrap" style="margin-bottom:12px;"><table><thead><tr><th>Job ID</th><th>Name</th><th>Status</th><th>Owner Worker</th><th>Lease TTL (s)</th><th>Attempts</th></tr></thead><tbody id="gx-jobs-body">{job_rows}</tbody></table></div>
  <div class="table-wrap"><table><thead><tr><th>DLQ Job ID</th><th>Name</th><th>Error Type</th><th>Attempts</th></tr></thead><tbody id="gx-dlq-body">{dlq_rows}</tbody></table></div>
</div>

<div class="section">
  <h2>Reactive Dependency Graph (SVG)</h2>
  <div style="background: #111827; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; overflow-x: auto;">
    {dag_svg}
  </div>
</div>

<div class="section">
  <h2>Recent Execution Traces</h2>
  <div class="table-wrap"><table><thead><tr><th>Time</th><th>Category</th><th>Operation</th><th>Session</th><th>Duration</th><th>Details</th></tr></thead><tbody>{traces_rows_html}</tbody></table></div>
</div>
</div>

<script>
(function() {{
  const refreshBtn = document.getElementById("gx-refresh-btn");
  const toggle = document.getElementById("gx-autorefresh-toggle");
  const intervalSel = document.getElementById("gx-autorefresh-interval");
  const lastRefreshEl = document.getElementById("gx-last-refresh");
  let timer = null;

  function esc(v) {{
    return String(v ?? "").replace(/[&<>\"']/g, function(c) {{
      return {{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c];
    }});
  }}
  function fmtMs(v) {{ return v === null || v === undefined ? "unavailable" : Number(v).toFixed(2) + " ms"; }}

  async function refreshAll() {{
    try {{
      const [rtRes, jobRes, sseRes] = await Promise.all([
        fetch("/_gx/inspect/runtime", {{ credentials: "same-origin" }}),
        fetch("/_gx/inspect/jobs?limit=25", {{ credentials: "same-origin" }}),
        fetch("/_gx/inspect/sse", {{ credentials: "same-origin" }})
      ]);
      if (!rtRes.ok || !jobRes.ok || !sseRes.ok) return;
      const rt = await rtRes.json();
      const jb = await jobRes.json();
      const sse = await sseRes.json();

      lastRefreshEl.textContent = rt.timestamp || new Date().toISOString();
      const badge = document.getElementById("gx-status-badge");
      badge.textContent = (rt.status || "unknown").toUpperCase();
      badge.className = "badge badge-" + (rt.status || "unavailable");

      const warnBox = document.getElementById("gx-warnings-box");
      if (rt.warnings && rt.warnings.length) {{
        warnBox.style.display = "block";
        warnBox.innerHTML = "<strong>Degradation Warnings:</strong><ul>" + rt.warnings.map(w => "<li>" + esc(w) + "</li>").join("") + "</ul>";
      }} else {{
        warnBox.style.display = "none";
      }}

      const r = rt.redis || {{}};
      document.getElementById("gx-redis-health").textContent = !r.configured ? "Local Mode" : (r.connected ? "Connected (" + r.ping_ms + " ms)" : "Unavailable");
      const cl = rt.cluster || {{}};
      document.getElementById("gx-active-workers").textContent = cl.active_workers ?? 0;
      document.getElementById("gx-sse-active").textContent = sse.metrics ? sse.metrics.active_connections : 0;
      document.getElementById("gx-jobs-depth").textContent = (jb.queue_depth ?? "unavailable") + " / " + (jb.active_count ?? "unavailable") + " / " + (jb.dlq_depth ?? "unavailable");

      const wBody = document.getElementById("gx-workers-body");
      const workers = cl.workers || [];
      wBody.innerHTML = workers.length ? workers.map(w =>
        "<tr><td>" + esc(w.worker_id) + "</td><td>" + esc(w.hostname) + " (" + esc(w.pid) + ")</td><td>" + esc(w.backend_mode) + "</td><td>" + esc(w.uptime_seconds ?? "n/a") + "s</td><td>" + esc(w.snapshot_age_seconds ?? "n/a") + "s</td><td><span class=\\"badge badge-" + esc(w.heartbeat_status) + "\\">" + esc(w.heartbeat_status) + "</span></td><td>" + esc(w.active_sse_connections ?? 0) + "</td></tr>"
      ).join("") : "<tr><td colspan=\\"7\\">No active workers registered</td></tr>";

      const gov = sse.governance || {{}};
      const ops = gov.operations || {{}};
      document.getElementById("gx-sse-body").innerHTML = "<tr><td>" + esc(gov.mode || "memory") + "</td><td>" + esc(ops.admitted || 0) + "</td><td>" + esc(ops.rejected_rate_limit || 0) + "</td><td>" + esc(ops.rejected_session_limit || 0) + "</td><td>" + esc(ops.rejected_ip_limit || 0) + "</td><td>" + esc(ops.leases_renewed || 0) + "</td><td>" + esc(ops.expired_leases || 0) + "</td><td>" + esc(ops.renewal_failures || 0) + "</td></tr>";

      const sLat = (cl.state && cl.state.latencies) || {{}};
      const eLat = (cl.events && cl.events.latencies) || {{}};
      const pairs = [["State get", sLat.get], ["State set", sLat.set], ["State CAS", sLat.cas], ["State delete", sLat.delete], ["Event publish", eLat.publish], ["Event replay", eLat.replay]];
      document.getElementById("gx-latency-body").innerHTML = pairs.map(([lbl, e]) =>
        e ? "<tr><td>" + lbl + "</td><td>" + esc(e.count || 0) + "</td><td>" + esc(e.errors || 0) + "</td><td>" + fmtMs(e.p50_ms) + "</td><td>" + fmtMs(e.p95_ms) + "</td><td>" + fmtMs(e.max_ms) + "</td></tr>"
          : "<tr><td>" + lbl + "</td><td colspan=\\"5\\">unavailable</td></tr>"
      ).join("");

      const aJobs = jb.active_jobs || [];
      document.getElementById("gx-jobs-body").innerHTML = aJobs.length ? aJobs.map(j =>
        "<tr><td>" + esc(j.job_id) + "</td><td>" + esc(j.name) + "</td><td>" + esc(j.status) + "</td><td>" + esc(j.owner_worker_id || "-") + "</td><td>" + esc(j.lease_remaining_seconds ?? "-") + "</td><td>" + esc(j.attempt) + "/" + esc(j.max_retries) + "</td></tr>"
      ).join("") : "<tr><td colspan=\\"6\\">No active jobs</td></tr>";

      const dJobs = jb.dlq_jobs || [];
      document.getElementById("gx-dlq-body").innerHTML = dJobs.length ? dJobs.map(j =>
        "<tr><td>" + esc(j.job_id) + "</td><td>" + esc(j.name) + "</td><td>" + esc(j.error_type || "unknown") + "</td><td>" + esc(j.attempt) + "</td></tr>"
      ).join("") : "<tr><td colspan=\\"4\\">DLQ empty</td></tr>";
    }} catch (_e) {{}}
  }}

  function resetTimer() {{
    if (timer) {{ clearInterval(timer); timer = null; }}
    if (toggle.checked) {{
      timer = setInterval(refreshAll, parseInt(intervalSel.value, 10) || 10000);
    }}
  }}

  refreshBtn.addEventListener("click", refreshAll);
  toggle.addEventListener("change", resetTimer);
  intervalSel.addEventListener("change", resetTimer);
}})();
</script>
</body></html>"""
