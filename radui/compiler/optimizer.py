from __future__ import annotations

import hashlib
import inspect
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from radui.compiler.analyzer import (
    CompilerDiagnostic,
    StaticDependencyReport,
    _analyze_handler_ast,
    analyze_component_tree,
    is_pure_static_subtree,
)
from radui.components.nodes import Component
from radui.renderers.html import HTMLRenderer


@dataclass(frozen=True)
class CompiledRoutePlan:
    route: str
    source_hash: str
    static_state_keys: tuple[str, ...]
    dependency_index: dict[str, tuple[str, ...]]  # state_key -> (component_id, ...)
    static_fragments: dict[str, str]  # component_id -> pre-rendered HTML
    has_dynamic_branches: bool
    diagnostics: tuple[CompilerDiagnostic, ...] = ()


@dataclass
class CompiledAppPlan:
    app_name: str
    content_hash: str
    compile_time_ms: float
    routes: dict[str, CompiledRoutePlan] = field(default_factory=dict)
    cache_hits: int = 0

    def to_manifest(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "content_hash": self.content_hash,
            "compile_time_ms": round(self.compile_time_ms, 3),
            "routes": {
                r: {
                    "source_hash": p.source_hash,
                    "static_state_keys": list(p.static_state_keys),
                    "dependency_index": {k: list(v) for k, v in p.dependency_index.items()},
                    "static_fragment_count": len(p.static_fragments),
                    "has_dynamic_branches": p.has_dynamic_branches,
                    "diagnostics": [{"level": d.level, "code": d.code, "message": d.message} for d in p.diagnostics],
                }
                for r, p in self.routes.items()
            },
        }


def _handler_source_hash(handler: Any) -> str:
    try:
        src = inspect.getsource(handler)
    except (OSError, TypeError):
        src = repr(handler)
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]


def compile_app(
    app: Any,
    *,
    cache_dir: str | Path | None = None,
) -> CompiledAppPlan:
    """Compile an App into a deterministic, content-addressed CompiledAppPlan."""
    t0 = time.perf_counter()
    renderer = getattr(app, "renderer", None) or HTMLRenderer()
    routes: dict[str, CompiledRoutePlan] = {}
    agg_hasher = hashlib.sha256()

    prior_cache: dict[str, Any] = {}
    cache_file = Path(cache_dir) / "compiled_manifest.json" if cache_dir is not None else None
    if cache_file is not None and cache_file.exists():
        try:
            prior_cache = json.loads(cache_file.read_text(encoding="utf-8")).get("routes", {})
        except Exception:
            prior_cache = {}

    cache_hits = 0
    for path, page in sorted(getattr(app, "_pages", {}).items()):
        s_hash = _handler_source_hash(page.handler)
        agg_hasher.update(f"{path}:{s_hash}".encode("utf-8"))
        ast_keys, dynamic, diags = _analyze_handler_ast(page.handler, path)
        dep_index: dict[str, set[str]] = {}
        static_frags: dict[str, str] = {}

        # Try safe static tree inspection for parameterless pages without side effects
        sig = inspect.signature(page.handler)
        if not sig.parameters:
            try:
                tree = page.handler()
                if isinstance(tree, Component):
                    tree_rep = analyze_component_tree(tree, route=path)
                    ast_keys.update(tree_rep.static_state_keys)
                    for cid, keys in tree_rep.component_deps.items():
                        for k in keys:
                            dep_index.setdefault(k, set()).add(cid)

                    def collect_frags(node: Component) -> None:
                        if node.id and is_pure_static_subtree(node):
                            static_frags[node.id] = renderer.render_component(node)
                            return
                        for ch in getattr(node, "children", ()):
                            collect_frags(ch)
                        for attr in ("first", "second"):
                            v = getattr(node, attr, None)
                            if isinstance(v, Component):
                                collect_frags(v)

                    collect_frags(tree)
            except Exception as exc:
                diags.append(CompilerDiagnostic("info", "DRY_RUN_SKIPPED", f"Static tree dry-run skipped: {exc}", path))

        if path in prior_cache and prior_cache[path].get("source_hash") == s_hash:
            cache_hits += 1

        routes[path] = CompiledRoutePlan(
            route=path,
            source_hash=s_hash,
            static_state_keys=tuple(sorted(ast_keys)),
            dependency_index={k: tuple(sorted(v)) for k, v in sorted(dep_index.items())},
            static_fragments=static_frags,
            has_dynamic_branches=dynamic,
            diagnostics=tuple(diags),
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    plan = CompiledAppPlan(
        app_name=app.metadata.name,
        content_hash=agg_hasher.hexdigest()[:16],
        compile_time_ms=elapsed_ms,
        routes=routes,
        cache_hits=cache_hits,
    )
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(plan.to_manifest(), indent=2), encoding="utf-8")
    return plan


def render_with_plan(
    root: Component,
    plan: CompiledRoutePlan | None,
    renderer: HTMLRenderer,
    *,
    state_context: Any = None,
    csrf_token: str | None = None,
) -> str:
    """Render a Component tree reusing precompiled static fragments when available (100% equivalent output)."""
    if plan is not None and root.id and root.id in plan.static_fragments and is_pure_static_subtree(root):
        return plan.static_fragments[root.id]
    return renderer.render_component(root, state_context=state_context, csrf_token=csrf_token)
