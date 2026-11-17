from __future__ import annotations

import asyncio
import inspect
import json
import secrets
from dataclasses import dataclass
from html import escape
from typing import Any, AsyncIterator

from radui.components.nodes import Component


@dataclass
class SuspenseTask:
    boundary_id: str
    resolver: Any
    timeout_s: float
    error_fallback: Component | None = None


def collect_suspense_boundaries(root: Component) -> list[SuspenseTask]:
    """Collect all Suspense boundaries from a Component tree."""
    tasks: list[SuspenseTask] = []
    idx = 0

    def walk(node: Component) -> None:
        nonlocal idx
        if node.kind == "suspense":
            idx += 1
            bid = getattr(node, "boundary_id", None) or node.id or f"gx-susp-{idx}"
            tasks.append(
                SuspenseTask(
                    boundary_id=bid,
                    resolver=getattr(node, "resolver", None),
                    timeout_s=float(getattr(node, "timeout_s", 5.0)),
                    error_fallback=getattr(node, "error_fallback", None),
                )
            )
            return
        for child in getattr(node, "children", ()):
            walk(child)
        for attr in ("first", "second"):
            val = getattr(node, attr, None)
            if isinstance(val, Component):
                walk(val)

    walk(root)
    return tasks


async def _resolve_boundary(
    task: SuspenseTask,
    renderer: Any,
    state_context: Any,
    csrf_token: str,
) -> tuple[str, str]:
    """Resolve a single Suspense boundary with timeout and error fallback."""
    try:
        res = task.resolver() if callable(task.resolver) else task.resolver
        if inspect.isawaitable(res):
            comp = await asyncio.wait_for(res, timeout=task.timeout_s)
        else:
            comp = await asyncio.wait_for(asyncio.to_thread(lambda: res), timeout=task.timeout_s)
        if not isinstance(comp, Component):
            raise TypeError("Suspense resolver must return a RadUI Component")
        html = renderer.render_component(comp, state_context=state_context, csrf_token=csrf_token)
        return task.boundary_id, html
    except Exception:
        if task.error_fallback is not None:
            err_html = renderer.render_component(task.error_fallback, state_context=state_context, csrf_token=csrf_token)
        else:
            err_html = '<div class="gx-suspense-error" role="status">Section unavailable</div>'
        return task.boundary_id, err_html


async def stream_page_html(
    *,
    shell_html: str,
    tasks: list[SuspenseTask],
    renderer: Any,
    state_context: Any,
    csrf_token: str,
    stream_nonce: str | None = None,
    is_disconnected: Any = None,
) -> AsyncIterator[bytes]:
    """Stream initial HTML shell immediately, then emit out-of-order <template> chunks."""
    nonce = stream_nonce or secrets.token_hex(12)
    closing = "</body></html>"
    if closing in shell_html:
        head_shell, tail_shell = shell_html.rsplit(closing, 1)
        tail_shell = closing + tail_shell
    else:
        head_shell, tail_shell = shell_html, ""

    # Inject stream nonce meta tag into <head> for client verification
    nonce_meta = f'<meta name="gx-stream-nonce" content="{escape(nonce, quote=True)}">'
    if "</head>" in head_shell:
        head_shell = head_shell.replace("</head>", f"{nonce_meta}</head>", 1)

    yield head_shell.encode("utf-8")

    if tasks:
        pending = [
            asyncio.create_task(_resolve_boundary(t, renderer, state_context, csrf_token))
            for t in tasks
        ]
        try:
            for fut in asyncio.as_completed(pending):
                if is_disconnected is not None:
                    try:
                        if await is_disconnected():
                            break
                    except Exception:
                        pass
                bid, html = await fut
                safe_bid = escape(bid, quote=True)
                safe_nonce = escape(nonce, quote=True)
                chunk = f'<template data-gx-stream-target="{safe_bid}" data-gx-stream-nonce="{safe_nonce}">{html}</template>'
                yield chunk.encode("utf-8")
        finally:
            for p in pending:
                if not p.done():
                    p.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    if tail_shell:
        yield tail_shell.encode("utf-8")
