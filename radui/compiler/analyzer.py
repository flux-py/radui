from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import dataclass, field
from typing import Any

from radui.components.nodes import Component


@dataclass(frozen=True)
class CompilerDiagnostic:
    level: str  # "info" | "warning" | "error"
    code: str
    message: str
    location: str = ""


@dataclass(frozen=True)
class StaticDependencyReport:
    route: str
    static_state_keys: tuple[str, ...]
    component_deps: dict[str, tuple[str, ...]]
    has_dynamic_branches: bool
    static_subtree_ids: tuple[str, ...]
    diagnostics: tuple[CompilerDiagnostic, ...] = ()


def detect_circular_dependencies(graph: dict[str, set[str] | tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Detect cycles in computed/state dependency graphs."""
    cycles: list[tuple[str, ...]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        visiting.add(node)
        stack.append(node)
        for nxt in graph.get(node, ()):
            if nxt in visiting:
                idx = stack.index(nxt)
                cycles.append(tuple(stack[idx:] + [nxt]))
            elif nxt not in visited:
                dfs(nxt)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for key in sorted(graph):
        if key not in visited:
            dfs(key)
    return cycles


def _analyze_handler_ast(handler: Any, route: str) -> tuple[set[str], bool, list[CompilerDiagnostic]]:
    """Inspect a Python page/layout handler AST for static state reads and dynamic branches."""
    keys: set[str] = set()
    dynamic = False
    diags: list[CompilerDiagnostic] = []
    try:
        src = textwrap.dedent(inspect.getsource(handler))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError) as exc:
        diags.append(CompilerDiagnostic("info", "AST_UNAVAILABLE", f"Falling back to runtime tracking: {exc}", route))
        return keys, True, diags

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ListComp)):
            dynamic = True
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            # e.g. state["count"] or ctx.state["count"]
            if isinstance(node.value, ast.Attribute) and node.value.attr == "state":
                keys.add(node.slice.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"read", "get"} and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.add(node.args[0].value)
    return keys, dynamic, diags


def is_pure_static_subtree(node: Component) -> bool:
    """Return True iff a Component subtree has no reactive bindings, islands, resumability, or async suspense."""
    if getattr(node, "state_ref", None) is not None or getattr(node, "binding_key", None):
        return False
    if getattr(node, "resumable", False) or getattr(node, "interactions", ()) or getattr(node, "local_state", None) or getattr(node, "bind_local", None):
        return False
    if node.kind in {"island", "suspense", "custom_element", "job_panel", "canvas_stream", "presence_bar"}:
        return False
    for child in getattr(node, "children", ()):
        if not is_pure_static_subtree(child):
            return False
    for attr in ("first", "second"):
        val = getattr(node, attr, None)
        if isinstance(val, Component) and not is_pure_static_subtree(val):
            return False
    return True


def analyze_component_tree(root: Component, route: str = "/") -> StaticDependencyReport:
    """Statically analyze a built Component AST for state dependencies and pure-static subtrees."""
    comp_deps: dict[str, set[str]] = {}
    all_keys: set[str] = set()
    static_ids: list[str] = []

    def walk(node: Component) -> None:
        cid = node.id or ""
        bkey = getattr(node, "binding_key", None)
        if bkey:
            all_keys.add(str(bkey))
            if cid:
                comp_deps.setdefault(cid, set()).add(str(bkey))
        sref = getattr(node, "state_ref", None)
        if sref is not None and getattr(sref, "key", None):
            k = str(sref.key)
            all_keys.add(k)
            if cid:
                comp_deps.setdefault(cid, set()).add(k)
        if cid and is_pure_static_subtree(node):
            static_ids.append(cid)
        for child in getattr(node, "children", ()):
            walk(child)
        for attr in ("first", "second"):
            val = getattr(node, attr, None)
            if isinstance(val, Component):
                walk(val)

    walk(root)
    return StaticDependencyReport(
        route=route,
        static_state_keys=tuple(sorted(all_keys)),
        component_deps={k: tuple(sorted(v)) for k, v in sorted(comp_deps.items())},
        has_dynamic_branches=False,
        static_subtree_ids=tuple(static_ids),
    )


def analyze_app_sources(app: Any) -> dict[str, StaticDependencyReport]:
    """Analyze all registered pages in an App using Python AST inspection."""
    reports: dict[str, StaticDependencyReport] = {}
    for path, page in getattr(app, "_pages", {}).items():
        keys, dynamic, diags = _analyze_handler_ast(page.handler, path)
        reports[path] = StaticDependencyReport(
            route=path,
            static_state_keys=tuple(sorted(keys)),
            component_deps={},
            has_dynamic_branches=dynamic,
            static_subtree_ids=(),
            diagnostics=tuple(diags),
        )
    return reports
