# M2.0–M2.3 Implementation Audit & Baseline

- **Branch:** `main`
- **HEAD Commit:** `ea96c7c`
- **Working Tree:** Preserved uncommitted M1.x–M1.9.2 changes across `radui/`, `tests/`, `docs/`, `README.md`, `CHANGELOG.md`, and `examples/`.

## 1. Baseline Verification Metrics

| Metric | Observed Baseline |
|---|---|
| Test Suite (pre-M1.9.2, live Redis `7.4.11`) | `335 passed in 144.10s` (0 failures, 0 skips) |
| M1.9.2 SPA Security & 1,050-Nav Memory Test | `1 passed in 3.99s` (listeners `62 -> 59`, nodes `74`, heap `0.79 MB -> 0.71 MB`) |
| `CLIENT_JS` Raw Size | `80,049 B` (`78.17 KiB`) |
| `CLIENT_JS` Gzip (level 9) | `18,620 B` (`18.18 KiB`) |
| `CLIENT_JS` Brotli (Node `zlib.brotliCompressSync`) | `16,152 B` (`15.77 KiB`) |
| Chrome Interaction Latency (`M1.8.1`, 500 clicks) | `p50 = 0.200 ms`, `p95 = 0.400 ms` |
| Chrome SPA Navigation (`M1.9.1`) | Uncached `p50 = 6.300 ms` / `p95 = 10.700 ms`; Prefetched `p50 = 0.800 ms` / `p95 = 1.200 ms` |
| 6-Tier Framework Benchmark (`benchmarks/run.py`) | Tier 1 `0.0323 ms`, Tier 2 `0.0806 ms`, Tier 3 `3.5957 ms`, Tier 4 `4.9191 ms`, Tier 5 `0.2314 ms`, Tier 6 `0.0096 ms` |

## 2. Core Architecture Inventory

- **Component AST & Builders:** `radui/components/nodes.py`, `radui/components/model_forms.py`, `radui/core/registry.py` (`71` public `Component`-returning builders, all supporting `local_state`, `interactions`, `bind_local`, and motion metadata).
- **Application IR & Core App:** `radui/core/ir.py`, `radui/core/app.py` (Starlette ASGI app, `@app.page`, `@app.layout`, `@app.command`, `@app.island`, `/_gx/navigate`, `/_gx/events`, `/_gx/commands/{id}`).
- **Renderer & Browser Runtime:** `radui/renderers/html.py` (`HTMLRenderer`, `CLIENT_JS` with `RadUIInteractions`, `RadUINavigator`, Hybrid Islands, Motion, `EventSource`, offline mutation queue), `radui/renderers/wasm.py`.
- **Reactive State & Dependencies:** `radui/state/runtime.py` (`StateRuntime`, `StateContext`), `radui/state/dependencies.py` (`DependencyTracker`), `radui/state/signals.py` (signals & computed), `radui/state/refs.py`, `radui/state/backend.py` (InMemory, SQLite, Redis, Postgres).
- **Interactions, Islands & SSG:** `radui/interactions.py` (16 events, 19 actions, 7 `bind_local` props), `radui/core/islands.py`, `radui/core/ssg.py`.
- **Distributed Governance, Jobs & Observability:** `radui/transport/events.py`, `radui/transport/governance.py`, `radui/jobs/redis.py`, `radui/observability.py`, `radui/diagnostics.py`, `radui/inspector/`.

## 3. Unified M2.0–M2.3 Target Architecture

```text
Python App -> Component AST -> Application IR -> M2.1 Compiler/Optimizer -> Execution Plan
                                                                               |
                                                       +-----------------------+-----------------------+
                                                       |                                               |
                                                  Initial SSR                                    M2.3 Streaming SSR
                                                       |                                               |
                                                       +-----------------------+-----------------------+
                                                                               |
                                         Browser Runtime (M2.0 Resumability + M1.8 + M1.9 + M1.3 Islands)
                                                                               |
                                                               M2.2 Web Components / Shadow DOM
                                                                               |
                                                        Python Server Commands / StateRuntime / Redis
```

## 4. Prioritized Implementation-Gap Matrix

| Milestone | Inspiration | Existing Foundation | Key Gaps to Implement |
|---|---|---|---|
| **M2.0** | Qwik | `data-gx-local-state`, `data-gx-interactions`, `Hybrid Islands`, `StateContext` | Versioned resumability schema (`radui/resumability/`), typed execution descriptors, lazy boundary restoration (`data-gx-resumable`), server validation & state migration, browser lazy activation |
| **M2.1** | Svelte | `radui/core/ir.py`, `DependencyTracker`, `radui/cli.py` | Python AST + IR static dependency analyzer (`radui/compiler/`), safe tree/static-fragment optimizations, `radui compile` / `radui build --optimize`, equivalence & cache invalidation |
| **M2.2** | Lit | `EMBED_JS` (`RADUI-view`), `ComponentRegistry`, `Theme` CSS variables | Python-first `@app.web_component` / `custom_element`, `radui/web_components/`, open/closed Shadow DOM + slot/CSS token bridge, typed custom event bridge with CSRF protection, SSR & resumability integration |
| **M2.3** | Marko | `HTMLRenderer`, `StreamingResponse` (SSE), `ErrorBoundary` | `suspense()` async rendering boundaries (`radui/streaming/`), progressive shell + out-of-order chunk streaming, bounded backpressure & cancellation, client progressive DOM swap, SSR/SSG fallback |
