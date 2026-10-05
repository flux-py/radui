"""RADUI Data Engine: SWR query caching, request deduplication, and cache invalidation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import functools
import inspect
import threading
import time
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class QueryEntry(Generic[T]):
    key: str
    data: T
    fetched_at: float
    stale_time: float
    error_count: int = 0
    in_flight: bool = False


def _run_coroutine_in_worker_thread(coro_fn: Callable[[], Any]) -> Any:
    """Run an async coroutine safely, avoiding event loop deadlock if called from an async thread."""
    coro = coro_fn()
    try:
        asyncio.get_running_loop()
        has_running_loop = True
    except RuntimeError:
        has_running_loop = False

    if not has_running_loop:
        return asyncio.run(coro)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=30.0)


class QueryCache:
    """Thread-safe SWR (Stale-While-Revalidate) in-memory query cache."""

    def __init__(self) -> None:
        self._entries: dict[str, QueryEntry[Any]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._master_lock = threading.Lock()

    def _get_lock(self, key: str) -> threading.Lock:
        with self._master_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def get(self, key: str) -> QueryEntry[Any] | None:
        with self._master_lock:
            return self._entries.get(key)

    def set(self, key: str, data: Any, stale_time: float) -> QueryEntry[Any]:
        entry = QueryEntry(
            key=key,
            data=data,
            fetched_at=time.time(),
            stale_time=stale_time,
            error_count=0,
            in_flight=False,
        )
        with self._master_lock:
            self._entries[key] = entry
        return entry

    def invalidate(self, key_or_prefix: str | None = None) -> int:
        """Invalidate queries matching key or prefix. If None, invalidate all."""
        with self._master_lock:
            if key_or_prefix is None:
                count = len(self._entries)
                self._entries.clear()
                return count
            keys_to_remove = [
                k for k in self._entries.keys()
                if k == key_or_prefix or k.startswith(f"{key_or_prefix}:") or k.startswith(f"{key_or_prefix}/")
            ]
            for k in keys_to_remove:
                del self._entries[k]
            return len(keys_to_remove)

    def execute_with_retry(self, fetch_fn: Callable[[], T], retry: int = 3) -> T:
        last_exc: Exception | None = None
        for attempt in range(max(1, retry)):
            try:
                if inspect.iscoroutinefunction(fetch_fn):
                    return _run_coroutine_in_worker_thread(fetch_fn)
                res = fetch_fn()
                if inspect.isawaitable(res):
                    return _run_coroutine_in_worker_thread(lambda: res)
                return res
            except Exception as exc:
                last_exc = exc
                time.sleep(0.05 * (2 ** attempt))
        if last_exc:
            raise last_exc
        raise RuntimeError("Query execution failed")

    async def aquery(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        stale_time: float = 60.0,
        retry: int = 3,
    ) -> Any:
        """Asynchronous data query with automatic SWR caching and deduplication."""
        now = time.time()
        entry = self.get(key)
        if entry is not None and (now - entry.fetched_at) < entry.stale_time:
            return entry.data

        # Background revalidation if stale
        if entry is not None and not entry.in_flight:
            entry.in_flight = True
            async def _bg_reval():
                try:
                    res = fetch_fn()
                    data = await res if inspect.isawaitable(res) else res
                    self.set(key, data, stale_time)
                except Exception:
                    pass
            asyncio.create_task(_bg_reval())
            return entry.data

        # Cache miss
        res = fetch_fn()
        data = await res if inspect.isawaitable(res) else res
        self.set(key, data, stale_time)
        return data

    def query(
        self,
        key: str,
        fetch_fn: Callable[[], T],
        stale_time: float = 60.0,
        retry: int = 3,
    ) -> T:
        """Fetch or revalidate data with request deduplication and SWR semantics."""
        now = time.time()
        entry = self.get(key)

        # 1. Cache hit & fresh
        if entry is not None and (now - entry.fetched_at) < entry.stale_time:
            return entry.data

        # 2. Lock for deduplicating concurrent fetches for the same key
        lock = self._get_lock(key)
        with lock:
            # Recheck inside lock
            entry = self.get(key)
            if entry is not None and (now - entry.fetched_at) < entry.stale_time:
                return entry.data

            # If entry exists but is stale, revalidate in background if not already in flight
            if entry is not None and not entry.in_flight:
                entry.in_flight = True
                def _bg_revalidate():
                    try:
                        new_data = self.execute_with_retry(fetch_fn, retry=1)
                        self.set(key, new_data, stale_time)
                    except Exception:
                        pass
                thread = threading.Thread(target=_bg_revalidate, daemon=True)
                thread.start()
                return entry.data

            # Cache miss: synchronous fetch
            data = self.execute_with_retry(fetch_fn, retry=retry)
            self.set(key, data, stale_time)
            return data


_GLOBAL_QUERY_CACHE = QueryCache()


def _resolve_tenant_query_key(key: str, explicit_tenant_id: str | None = None) -> str:
    from radui.state.runtime import get_active_context
    active_ctx = get_active_context()
    resolved_tenant = explicit_tenant_id or (active_ctx.tenant_id if active_ctx else None)
    return f"t:{resolved_tenant}:{key}" if resolved_tenant else key


def query(
    key: str,
    fetch_fn: Callable[[], T],
    stale_time: float = 60.0,
    retry: int = 3,
    tenant_id: str | None = None,
) -> T:
    """Execute a data query with automatic SWR caching and request deduplication.
    
    Automatically derives tenant isolation from active StateContext when present.
    """
    effective_key = _resolve_tenant_query_key(key, tenant_id)
    return _GLOBAL_QUERY_CACHE.query(effective_key, fetch_fn, stale_time=stale_time, retry=retry)


async def aquery(
    key: str,
    fetch_fn: Callable[[], Any],
    stale_time: float = 60.0,
    retry: int = 3,
    tenant_id: str | None = None,
) -> Any:
    """Asynchronously execute a data query with SWR caching and deduplication.
    
    Automatically derives tenant isolation from active StateContext when present.
    """
    effective_key = _resolve_tenant_query_key(key, tenant_id)
    return await _GLOBAL_QUERY_CACHE.aquery(effective_key, fetch_fn, stale_time=stale_time, retry=retry)


def invalidate_query(
    key_or_prefix: str | None = None,
    tenant_id: str | None = None,
) -> int:
    """Invalidate query cache entries matching key or prefix.
    
    Automatically scopes invalidation to the active tenant when present.
    """
    from radui.state.runtime import get_active_context
    active_ctx = get_active_context()
    resolved_tenant = tenant_id or (active_ctx.tenant_id if active_ctx else None)
    if resolved_tenant:
        effective_prefix = f"t:{resolved_tenant}:{key_or_prefix}" if key_or_prefix else f"t:{resolved_tenant}:"
        return _GLOBAL_QUERY_CACHE.invalidate(effective_prefix)
    return _GLOBAL_QUERY_CACHE.invalidate(key_or_prefix)


def cached(ttl: float = 60.0, key: str | None = None):
    """Decorator to cache function results with SWR query caching."""
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        cache_key_base = key or f"{fn.__module__}:{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            args_str = ":".join(str(a) for a in args)
            kwargs_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            computed_key = f"{cache_key_base}:{args_str}:{kwargs_str}".rstrip(":")
            return query(computed_key, lambda: fn(*args, **kwargs), stale_time=ttl)

        return wrapper

    return decorator


def paginate(
    items: list[T] | tuple[T, ...],
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[T], int, int]:
    """Helper for paginating datasets. Returns (page_items, total_pages, total_items)."""
    total = len(items)
    page_size = max(1, page_size)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return list(items[start:end]), total_pages, total
