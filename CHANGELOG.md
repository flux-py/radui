# RADUI Framework Changelog

## [0.9.0] - 2026-11-15

### Added
- **68 Core Component Primitives (Component Expansion)**:
  - Added 19 modern UI components exceeding the 60+ component target:
    - `Toast` & `ToastContainer`: Real-time notification cards with auto-dismiss timers and stacked placement.
    - `Tooltip`: Accessible hover & focus hint wrappers.
    - `Popover`: Anchored floating panels with trigger button.
    - `Accordion` & `AccordionItem`: Collapsible disclosure sections with smooth transitions.
    - `Drawer`: Slide-out side panel modals (left, right, top, bottom).
    - `Breadcrumb` & `BreadcrumbItem`: Accessible hierarchical navigation trails.
    - `Pagination`: Page navigation buttons with current/total indicators.
    - `ProgressBar`: Determinate and indeterminate progress bars with percentage text, striped patterns, and animated shimmer.
    - `ProgressCircle`: SVG circular gauge with percentage indicator.
    - `Avatar` & `AvatarGroup`: User profile pictures with initials fallback, status badges, and grouped overflow indicators (`+2`).
    - `DatePicker`: Accessible date selector bound to reactive state.
    - `TimePicker`: Accessible time selector bound to reactive state.
    - `Slider`: Range slider input with live value preview label.
    - `SplitPanel`: Resizable horizontal and vertical split panes with draggable separator handle.
    - `DropdownMenu` & `DropdownMenuItem`: Action dropdowns with icons, shortcuts, and destructive styling.
    - `Kbd`: Styled keyboard shortcut key badges.
    - `Container`: Centered responsive max-width layout wrapper.
    - `Stack`: Flexible vertical and horizontal spacing container.
    - `Tag`: Dismissible and categorized feature tags/chips.
- **RADUI Data Engine (`RADUI.data`)**:
  - `gx.query(key, fetch_fn, stale_time=60, retry=3)`: SWR query caching engine with concurrent request deduplication.
  - `@gx.cached(ttl=60)`: Function decorator for server-side query caching.
  - `gx.invalidate_query(key_or_prefix)`: Cache invalidation triggering instant client re-renders.
  - `gx.paginate(items, page, page_size)`: Utility for dataset slicing and pagination metadata.
  - `gx.download_button(...)`: Client-side file download trigger.
- **Persistent Nested Route Layouts (`@app.layout`)**:
  - `@app.layout(path_prefix="/...")`: Hierarchical layout wrappers wrapping child page outlets (`outlet=page_root`) without duplicating navigation or shells across routes.
- **Distributed Production Providers**:
  - `RedisStateBackend`: Redis-backed distributed state storage for multi-worker / multi-pod deployments.
  - `PostgreSQLStateBackend`: Relational persistent state storage.
  - `RedisJobBackend`: Distributed job backend with lease acquisition, heartbeats, and worker broadcast.
- **Toast Notifications & Real-Time Dispatch (`app.notify`)**:
  - `app.notify(message, title, variant, duration)`: Publishes real-time toast notifications via SSE stream (`gx:toast`) rendered dynamically on the client.
- **Scroll Reveal Animations**:
  - `[data-gx-reveal]` with `IntersectionObserver` triggering hardware-accelerated entry animations when elements enter viewport.
- **Offline Mutation Queue**:
  - Automatic buffering of client form submissions and actions during network disconnections, with automatic replay on reconnect.
- **Internationalization (RTL)**:
  - `Theme(direction="rtl")` generating `dir="rtl"` and logical CSS direction rules.
- **Automated A11y & Quality Auditor CLI**:
  - `RADUI audit [app.py] --a11y`: Scans routes for heading hierarchies, form input labels, theme contrast, and ARIA live regions.
- **Static Site Generation (SSG)**:
  - `RADUI export [app.py] --static`: Generates full standalone HTML document bundles ready for CDN deployment.

### Added
- **Dynamic Routing & Path Parameters**:
  - Full path template matching: `@app.page("/users/{user_id}")` and `@app.page("/orgs/{org}/repos/{repo}")`.
  - Type-safe signature introspection automatically extracting and injecting path parameters into page handlers.
  - Route guards: `@app.page("/admin", require_auth=True, require_role="admin", require_permission="...")` blocking unauthorized access with standard 401/403 responses.
- **Pluggable Multi-Worker State Backend (`StateBackend`)**:
  - `InMemoryStateBackend`: High-throughput, thread-safe in-memory store for single-process runtimes and tests.
  - `SQLiteStateBackend`: Crash-resilient, multi-worker persistent state backend in SQLite WAL mode. Allows multiple Uvicorn workers and container restarts to share synchronized `user`, `session`, and `app` state.
- **Component-Level Error Boundary (`ErrorBoundary` / `gx.error_boundary`)**:
  - Gracefully isolates individual component rendering errors without crashing the entire page or surrounding layout.
  - Displays localized error banner with custom fallback message and instant [Retry] trigger.
- **Accessible Modal Focus Trap & ARIA Hardening**:
  - Enhanced client-side modal lifecycle with automatic focus acquisition on open and focus restoration to the trigger element on close (`Escape` or backdrop click).
  - Keyboard `Tab` focus trap preventing focus escape outside open dialogs.
  - Injected `role="dialog"`, `aria-modal="true"`, and `aria-labelledby` semantics.
- **Offline Detection & Reconnection Status Banner**:
  - Automatic browser `online` / `offline` event monitoring.
  - Dedicated client status banner (`.gx-connection-banner`) alerting users to network disconnects and auto-dismissing upon SSE reconnection.
- **Registry & Catalog Alignment**:
  - Synchronized component catalog dynamically introspected from `ComponentRegistry.builtins()` (44 registered built-in components).

## [0.7.0] - 2026-11-15

### Added
- **Global `Ctrl+K` Command Palette**:
  - Built-in keyboard-driven command navigation palette with search filtering, arrow navigation, Enter trigger, and Esc close.
  - Pre-wired shortcuts for navigation, page transitions, and theme toggling.
- **Responsive Layout Engine & Breakpoints**:
  - `Grid` accepts responsive breakpoint mappings: `columns={"sm": 1, "md": 2, "lg": 4}`.
  - Generates `--gx-cols-{bp}` responsive CSS variables paired with clean `@media` queries without inline JavaScript.
- **Native Design System & Theming (`RADUI.core.theme` / `gx.Theme`)**:
  - First-class `Theme` engine with token serialization, CSS variable compilation, and runtime theme switching.
  - Built-in theme presets: `Theme.dark()`, `Theme.indigo()`, `Theme.emerald()`, `Theme.zinc()`.
  - `ThemeToggle` (`gx.theme_toggle`) component with client-side theme switching and `localStorage` persistence.
- **Universal UI State Primitives**:
  - `Skeleton` (`gx.skeleton`): Shimmering placeholders (`@keyframes gx-shimmer`) with customizable shapes (`text`, `rect`, `circle`) and dimensions.
  - `EmptyState` (`gx.empty_state`): First-class zero-data UI state with visual icon, heading, description, and call-to-action.
- **Form-from-Model Reflection (`form_from_model`)**:
  - Automatic conversion of Pydantic models into typed RADUI forms.
  - Inferred types: booleans $\to$ checkboxes, Enums $\to$ dropdown selects, ints/floats $\to$ number inputs, passwords $\to$ masked inputs, descriptions $\to$ textareas.
  - Pre-populates bound `StateRef` references and defaults.
- **High-Performance Virtual List (`VirtualList` / `gx.virtual_list`)**:
  - Windowed DOM rendering engine capable of scrolling 50,000+ items at 60fps.
  - Dynamic scroll translation with sized spacer container and viewport clipping.
- **Drag-and-Drop File Upload (`FileUpload` / `gx.file_upload`)**:
  - Client-side drag-and-drop dropzone with file type and size constraints, progress styling, and file list previews.
- **Declarative Testing Harness (`RADUI.testing.TestHarness`)**:
  - Headless component and full-stack application testing harness.
  - Form extraction (`extract_form`, `get_forms`), headless page rendering (`get_page`, `render`), command dispatching (`dispatch`), and DOM assertions.
- **Micro-Frontend Embed Endpoint (`/_gx/embed.js`)**:
  - Lightweight Web Component `<RADUI-view>` for embedding RADUI views into external React, Vue, Angular, or standard HTML web apps.
- **Accessibility & A11y Polish**:
  - Dedicated `aria-live="polite"` polite announcer region for screen-reader notifications during real-time SSE patch updates.
  - System-wide `prefers-reduced-motion` compliance.

## [0.6.0] - 2026-11-14

### Added
- **Native Motion & Visual Interaction Engine (`RADUI.motion` / `gx.motion`)**:
  - **Zero-Dependency WAAPI Driver**: Bundled analytical spring physics solver and Web Animations API executor with zero external CDN requirements.
  - **Damped Harmonic Oscillator Physics**: Configurable `spring(stiffness, damping, mass)` generating hardware-accelerated 120fps motion curves.
  - **FLIP Layout Interpolation**: Intercepts `applyPatches` and smoothly transitions DOM replacements using First, Last, Invert, Play algorithms.
  - **Animated Number Tweening**: Seamless counter rolling for `MetricCard` value updates (`animate_number=True`).
  - **Micro-Interactions**: Declarative pointer hover elevation (`hover=gx.motion.hover(...)`) and tactile tap depression (`tap=gx.motion.tap(...)`).
  - **Staggered Container Cascades**: Cascaded delay animations for children in `Grid`, `Column`, and `TreeView` (`stagger_children=0.05`).
  - **View Transitions API Integration**: Seamless page-level transitions via native `document.startViewTransition`.
  - **Accessibility Compliance**: Built-in OS-level `prefers-reduced-motion` safety enforcement.
- **SQLite WAL Job Backend (`SQLiteJobBackend`)**:
  - Durable, file-backed background task execution with multi-process query persistence.
  - Automatic process-restart recovery marking interrupted jobs without data loss.
- **Built-in Auth & Role-Based Access Control (RBAC)**:
  - `@app.command(require_auth=True)`, `@app.command(require_role="admin")`, `@app.require_auth`, `@app.require_role(...)`.
  - First-class `User` and `RBACPolicy` models with inherited permissions.
- **Optimistic UI Signals & Rollback**:
  - Instantaneous client-side feedback on form/action submission with automatic rollback on network failure or 4xx/5xx responses.
- **Scoped GenerativeSlot Mutations**:
  - Isolated sub-rendering and incremental streaming updates for AI components without parent tree re-renders.

## [0.5.0] - 2026-11-14

### Added
- **Interactive Architecture Diagram & Flowchart Engine**:
  - `Diagram`, `DiagramNode`, `DiagramEdge` models and factory helpers.
  - Zero-dependency pure SVG rendering with smooth cubic bezier curves and directional arrow markers.
  - Animated flowlines (`animated=True`), pulsing status beacons (`active`, `success`, `warning`, `danger`), and custom shapes (`pill`, `diamond`, `database`, `rounded`).
  - Bi-directional node click triggers dispatching RADUI commands with structured payload.
- **Developer & Enterprise Component Suite**:
  - `CodeBlock`: Monospace presentation with line numbers, copy-to-clipboard, and language badges.
  - `TreeView` & `TreeNode`: Collapsible directory, AST, and component hierarchy trees with expand/collapse carets.
  - `DataGrid`: Advanced client-side searchable, sortable, and paginated data table.
  - `GenerativeSlot`: Container slot for dynamic agent-generated or runtime-swapped UI components.
- **CLI Runner & Library Distribution (`radui`)**:
  - `RADUI run <app.py> --port 8000 --reload` for running any RADUI app on a specified port.
  - `RADUI info` displaying system information and component registry stats.
  - `RADUI new <name>` scaffolding new RADUI applications.
  - `[project.scripts]` registration in `pyproject.toml` and `python -m RADUI` support.
- **Expanded Component Catalog**:
  - Layout & Containers: `Grid`, `Badge`, `Callout`, `Spacer`, `Tabs`, `TabItem`, `Modal`.
  - Advanced Form Controls: `Textarea`, `Select`, `Switch`, `RadioGroup`.
  - Analytics & Data: `MetricCard`, `Table`, `Plot` (with zero-dependency pure SVG bar and line rendering).
  - AI & Agent Native: `ChatView`, `ChatMessage`, `ChatInput`, `StreamingText`, `ActionCard`, `StepTimeline`, `DynamicCard`.
- **Runtime Inspector & Telemetry**:
  - `TraceCollector` recording circular telemetry logs for `render`, `state`, `command`, `job`, and `error`.
  - Built-in developer endpoints: `/_gx/inspect`, `/_gx/inspect/traces`, `/_gx/inspect/stats`.
  - Inline collapsible developer drawer (toggle with `Ctrl+Shift+I` or badge click).
- **AI & Agent Subsystem (`RADUI.ai`)**:
  - `StreamingFenceParser` for real-time extraction of structured UI blocks from streaming LLM output.
  - `a2ui_to_component` mapping external agent UI schemas to RADUI native component nodes.
  - `AGUIEventJournal` for tracking agent execution steps and generating reactive timelines.
  - `MCPToolRegistry` with human-in-the-loop validation support.
- **Modern Responsive Design System**:
  - Comprehensive CSS variables with light and dark mode support.
  - Interactive client-side tab switching, modal dialogs, and action card dispatchers.
- **Three Showcase Applications**:
  - `examples/ai_agent_workbench`: Full-stack agent workbench with streaming chat, background RAG indexing, execution journals, and action approval cards.
  - `examples/analytics_dashboard`: Multi-region executive BI cockpit with reactive filtering, metric cards, pure SVG charts, and OLAP refresh jobs.
  - `examples/saas_admin`: Multi-route administrative governance platform with user management, tabbed settings, and backup tasks.

## [0.4.0] - Prior Milestone
- Background job backend, progress tracking, cancellation endpoints, and `JobPanel` component.

## [0.3.0] - Prior Milestone
- Interactive forms, commands, CSRF protection, idempotency cache, and SSE event streaming.

## [0.2.0] - Prior Milestone
- Multi-scoped reactive state (`view`, `session`, `user`, `app`) and fine-grained dependency tracking.

## [0.1.0] - Prior Milestone
- Initial Application IR and HTML renderer.
