from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import radui as gx
from radui.compiler import (
    analyze_app_sources,
    analyze_component_tree,
    compile_app,
    detect_circular_dependencies,
    render_with_plan,
)
from radui.renderers.html import HTMLRenderer


def test_compiler_static_analysis_cycles_equivalence_and_cache(tmp_path: Path):
    # 1. Circular dependency detection
    cycles = detect_circular_dependencies({"a": {"b"}, "b": {"c"}, "c": {"a"}, "x": {"y"}})
    assert any("a" in cyc and "c" in cyc for cyc in cycles)

    # 2. App compilation + equivalence + incremental cache
    app = gx.App("M21CompiledApp")
    s_count = gx.state("count", 0)

    @app.page("/static")
    def static_page():
        return gx.column(
            *[gx.text(f"Item {i}", id=f"st-{i}") for i in range(40)],
            id="static-panel",
        )

    @app.page("/dynamic")
    def dynamic_page():
        flag = True
        items = [gx.text("Static")]
        if flag:
            items.append(gx.text(s_count, id="dyn-count"))
        return gx.column(*items, id="dyn-root")

    src_reports = analyze_app_sources(app)
    assert src_reports["/dynamic"].has_dynamic_branches is True

    cache_dir = tmp_path / ".radui-cache"
    plan1 = compile_app(app, cache_dir=cache_dir)
    assert plan1.cache_hits == 0
    assert "static-panel" in plan1.routes["/static"].static_fragments
    assert "dyn-count" in plan1.routes["/dynamic"].dependency_index.get("count", ())
    assert (cache_dir / "compiled_manifest.json").exists()

    # Exact HTML equivalence check
    renderer = HTMLRenderer()
    tree = static_page()
    assert render_with_plan(tree, plan1.routes["/static"], renderer) == renderer.render_component(tree)

    # Second compile hits content-addressed cache
    plan2 = compile_app(app, cache_dir=cache_dir)
    assert plan2.cache_hits == 2

    # Benchmark compiled fragment reuse vs full render_component (500 iterations)
    t0 = time.perf_counter()
    for _ in range(500):
        renderer.render_component(tree)
    uncompiled_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    for _ in range(500):
        render_with_plan(tree, plan1.routes["/static"], renderer)
    compiled_ms = (time.perf_counter() - t1) * 1000.0

    assert compiled_ms < uncompiled_ms
    print(f"\n[M2.1 Telemetry] compile={plan1.compile_time_ms:.2f}ms | 500x uncompiled={uncompiled_ms:.2f}ms vs compiled={compiled_ms:.2f}ms")


def test_cli_compile_and_build_optimize(tmp_path: Path):
    app_file = tmp_path / "sample_app.py"
    app_file.write_text(
        """import radui as gx
app = gx.App("CLICompileApp")
@app.page("/")
def index():
    return gx.column(gx.heading("Hello", id="h1"), id="root-col")
""",
        encoding="utf-8",
    )
    cache_out = tmp_path / ".cache"
    res_compile = subprocess.run(
        [sys.executable, "-m", "radui.cli", "compile", str(app_file), "--out-dir", str(cache_out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[OK] Compiled 'CLICompileApp'" in res_compile.stdout
    manifest = json.loads((cache_out / "compiled_manifest.json").read_text(encoding="utf-8"))
    assert "/" in manifest["routes"]

    dist_out = tmp_path / "dist"
    res_build = subprocess.run(
        [sys.executable, "-m", "radui.cli", "build", str(app_file), "--output", str(dist_out), "--optimize"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[OPT] Compiled" in res_build.stdout
    assert "[OK] Built" in res_build.stdout
