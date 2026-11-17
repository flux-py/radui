# ADR-016: Compiler-Assisted Reactive Optimization (M2.1)

- **Status:** Accepted (M2.1)
- **Context:** Repeatedly serializing large pure-static component subtrees and discovering static state dependencies at runtime adds avoidable CPU work, while transpiling Python to JS would break RadUI's Python-first security and state model.
- **Decision:** Introduce `radui/compiler/` (`analyzer.py`, `optimizer.py`) to inspect Python AST + Component AST into `CompiledAppPlan` (indexed dependencies, circular dependency diagnostics, pure-static HTML fragment reuse, and content-addressed caching), integrated with `radui compile` and `radui build --optimize`.
- **Consequences:** Static subtrees reuse pre-rendered HTML with exact output equivalence (`render_with_plan`) while dynamic branches and runtime `DependencyTracker` remain intact.
