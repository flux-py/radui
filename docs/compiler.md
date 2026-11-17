# RadUI Compiler-Assisted Reactive Optimization (M2.1)

RadUI M2.1 adds a Python-native compile-time analysis and optimization layer (`radui/compiler/`) that accelerates static subtrees and indexes reactive dependencies without transpiling Python to JavaScript or replacing the runtime `DependencyTracker`.

## 1. Architecture & Pipeline

1. **Python AST Analysis (`analyze_app_sources`):** Inspects `@app.page` handlers to identify state reads and control-flow branches (`if`, `for`, `while`, comprehensions -> `has_dynamic_branches=True` so runtime dependency tracking is always preserved).
2. **Component AST Analysis (`analyze_component_tree`):** Indexes `state_ref` and `binding_key` dependencies (`state_key -> tuple[component_id, ...]`) and detects circular dependencies (`detect_circular_dependencies`).
3. **Pure Static Subtree Caching (`compile_app`, `render_with_plan`):** Subtrees with zero reactive bindings, islands, resumable boundaries, interactions, or suspense (`is_pure_static_subtree`) are pre-rendered into deterministic HTML fragments with 100% output equivalence.
4. **Content-Addressed Incremental Cache:** `compile_app(..., cache_dir=".radui-cache")` writes `compiled_manifest.json` keyed by per-route SHA-256 `source_hash`.

## 2. CLI Commands

- `radui compile app.py --out-dir .radui-cache`
- `radui build app.py --output ./dist --optimize`

Compilation is strictly optional; uncompiled development workflows continue running on the standard runtime unchanged.
