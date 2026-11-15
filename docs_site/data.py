"""RADUI Documentation Website — Central Data Catalog & Metadata Definitions.

Contains metadata, parameters, descriptions, and code examples for all 68 built-in components,
45 CLI subcommands, 12 Architecture Decision Records, and global search index.
"""

from __future__ import annotations
from typing import Any

# =========================================================================
# 1. COMPONENT METADATA CATALOG (All 68 Built-in AST Primitives)
# =========================================================================

COMPONENT_DOMAINS = [
    "Layout & Disclosure",
    "Typography & Code",
    "Action & Trigger",
    "Form & Data Input",
    "Feedback & Overlays",
    "Navigation",
    "Data Display & Tables",
    "Indicators & Avatars",
    "Diagrams & Trees",
    "AI Agent & Workflow",
]

COMPONENTS: list[dict[str, Any]] = [
    # 1. Layout & Disclosure Primitives (12)
    {
        "name": "column",
        "domain": "Layout & Disclosure",
        "description": "Vertical flexbox container arranging child components top-to-bottom.",
        "params": [
            {"name": "gap", "type": "int", "default": 16, "description": "Spacing between children in pixels."},
            {"name": "align", "type": "str", "default": "stretch", "options": ["stretch", "start", "center", "end"], "description": "Cross-axis alignment."},
            {"name": "justify", "type": "str", "default": "start", "options": ["start", "center", "end", "between"], "description": "Main-axis justification."},
        ],
        "example": 'ui.column(\n    ui.heading("User Profile", level=2),\n    ui.text("Manage account security and permissions."),\n    ui.button("Save Changes", variant="primary"),\n    gap=16,\n)',
    },
    {
        "name": "row",
        "domain": "Layout & Disclosure",
        "description": "Horizontal flexbox container with alignment, spacing, and wrapping controls.",
        "params": [
            {"name": "gap", "type": "int", "default": 16, "description": "Spacing between children in pixels."},
            {"name": "align", "type": "str", "default": "center", "options": ["center", "start", "end", "stretch"], "description": "Cross-axis alignment."},
            {"name": "wrap", "type": "bool", "default": False, "description": "Whether children wrap onto multiple lines."},
        ],
        "example": 'ui.row(\n    ui.button("Cancel", variant="secondary"),\n    ui.button("Submit", variant="primary"),\n    gap=12,\n)',
    },
    {
        "name": "grid",
        "domain": "Layout & Disclosure",
        "description": "Responsive CSS Grid container with column counts and responsive breakpoints.",
        "params": [
            {"name": "columns", "type": "int", "default": 3, "description": "Number of columns or breakpoint dictionary."},
            {"name": "gap", "type": "int", "default": 16, "description": "Grid gutter spacing in pixels."},
        ],
        "example": 'ui.grid(\n    ui.card(ui.text("Metric A")),\n    ui.card(ui.text("Metric B")),\n    ui.card(ui.text("Metric C")),\n    columns=3,\n    gap=16,\n)',
    },
    {
        "name": "container",
        "domain": "Layout & Disclosure",
        "description": "Centered structural page wrapper with max-width and horizontal margins.",
        "params": [
            {"name": "max_width", "type": "str", "default": "1200px", "description": "Maximum width constraint."},
            {"name": "padding", "type": "int", "default": 16, "description": "Padding in pixels."},
        ],
        "example": 'ui.container(\n    ui.heading("Dashboard Overview", level=1),\n    ui.text("Welcome to RADUI portal."),\n    max_width="1200px",\n)',
    },
    {
        "name": "stack",
        "domain": "Layout & Disclosure",
        "description": "Flexible wrapping layout for button strips, tag clouds, and badge rows.",
        "params": [
            {"name": "direction", "type": "str", "default": "horizontal", "options": ["horizontal", "vertical"], "description": "Flow direction."},
            {"name": "gap", "type": "int", "default": 8, "description": "Item spacing in pixels."},
            {"name": "wrap", "type": "bool", "default": True, "description": "Whether items wrap onto next line."},
        ],
        "example": 'ui.stack(\n    ui.badge("Python"),\n    ui.badge("ASGI"),\n    ui.badge("SSE"),\n    gap=8,\n)',
    },
    {
        "name": "split_panel",
        "domain": "Layout & Disclosure",
        "description": "Resizable two-pane layout with draggable divider for master-detail views.",
        "params": [
            {"name": "direction", "type": "str", "default": "horizontal", "options": ["horizontal", "vertical"], "description": "Split orientation."},
            {"name": "initial_ratio", "type": "float", "default": 0.5, "description": "Initial split ratio between 0.1 and 0.9."},
        ],
        "example": 'ui.split_panel(\n    left=ui.card(ui.text("Navigation List")),\n    right=ui.card(ui.text("Detail View")),\n    initial_ratio=0.35,\n)',
    },
    {
        "name": "card",
        "domain": "Layout & Disclosure",
        "description": "Structured visual container panel with optional title, description, and footer.",
        "params": [
            {"name": "title", "type": "str", "default": "Server Telemetry", "description": "Card header title."},
            {"name": "subtitle", "type": "str", "default": "Real-time metrics", "description": "Subtitle description."},
        ],
        "example": 'ui.card(\n    ui.metric_card("Throughput", "1,420 rps"),\n    title="API Cluster Status",\n    subtitle="Updated 1s ago",\n)',
    },
    {
        "name": "dynamic_card",
        "domain": "Layout & Disclosure",
        "description": "Reactive card container observing a StateRef and re-rendering on mutations.",
        "params": [
            {"name": "title", "type": "str", "default": "Live Signal", "description": "Card header title."},
            {"name": "bind", "type": "str", "default": "s_count", "description": "StateRef variable to observe."},
        ],
        "example": 'ui.dynamic_card("Live State Viewer", bind=s_count,\n    ui.text("Content dynamically re-evaluates on state mutation.")\n)',
    },
    {
        "name": "accordion",
        "domain": "Layout & Disclosure",
        "description": "Collapsible disclosure container organizing vertically stacked expandable panels.",
        "params": [],
        "example": 'ui.accordion(\n    ui.accordion_item("Section 1", ui.text("Content 1"), open=True),\n    ui.accordion_item("Section 2", ui.text("Content 2")),\n)',
    },
    {
        "name": "accordion_item",
        "domain": "Layout & Disclosure",
        "description": "Individual collapsible section with interactive header toggle and body.",
        "params": [
            {"name": "title", "type": "str", "default": "Architecture FAQ", "description": "Accordion item header title."},
            {"name": "open", "type": "bool", "default": False, "description": "Initial expanded state."},
        ],
        "example": 'ui.accordion_item("How does SSR work?",\n    ui.text("Initial requests render complete HTML in under 3.1ms."),\n    open=True\n)',
    },
    {
        "name": "spacer",
        "domain": "Layout & Disclosure",
        "description": "Explicit layout spacing element creating vertical or horizontal margin.",
        "params": [
            {"name": "size", "type": "int", "default": 16, "description": "Spacing size in pixels."},
        ],
        "example": 'ui.spacer(size=24)',
    },
    {
        "name": "divider",
        "domain": "Layout & Disclosure",
        "description": "Structural visual separator rule segmenting sections within columns or rows.",
        "params": [
            {"name": "direction", "type": "str", "default": "horizontal", "options": ["horizontal", "vertical"], "description": "Divider orientation."},
        ],
        "example": 'ui.divider(direction="horizontal")',
    },

    # 2. Typography & Code Primitives (5)
    {
        "name": "heading",
        "domain": "Typography & Code",
        "description": "Semantic typography element rendering h1 through h6 with hierarchy validation.",
        "params": [
            {"name": "text", "type": "str", "default": "Application Architecture", "description": "Heading text."},
            {"name": "level", "type": "int", "default": 1, "options": [1, 2, 3, 4, 5, 6], "description": "HTML heading level."},
        ],
        "example": 'ui.heading("Reactive Execution Lifecycle", level=2)',
    },
    {
        "name": "text",
        "domain": "Typography & Code",
        "description": "Text display component supporting variants: body, caption, code, lead, muted.",
        "params": [
            {"name": "content", "type": "str", "default": "RADUI compiles pure Python declarative ASTs.", "description": "Text content."},
            {"name": "variant", "type": "str", "default": "body", "options": ["body", "caption", "code", "lead", "muted"], "description": "Typography style variant."},
        ],
        "example": 'ui.text("Sub-DOM diffing completes in 0.168 ms.", variant="lead")',
    },
    {
        "name": "callout",
        "domain": "Typography & Code",
        "description": "Highlighted informational callout banner with status semantics.",
        "params": [
            {"name": "title", "type": "str", "default": "Architecture Note", "description": "Banner title."},
            {"name": "message", "type": "str", "default": "Zero npm dependencies required.", "description": "Banner message."},
            {"name": "variant", "type": "str", "default": "info", "options": ["info", "success", "warning", "danger"], "description": "Callout visual style."},
        ],
        "example": 'ui.callout("Production Ready", "All 6 benchmark tiers verified.", variant="success")',
    },
    {
        "name": "code_block",
        "domain": "Typography & Code",
        "description": "Syntax-formatted monospace code block featuring line numbers and copy button.",
        "params": [
            {"name": "code", "type": "str", "default": "import radui as ui\napp = ui.App('Demo')", "description": "Source code text."},
            {"name": "language", "type": "str", "default": "python", "description": "Programming language."},
            {"name": "line_numbers", "type": "bool", "default": True, "description": "Display line numbering."},
            {"name": "copyable", "type": "bool", "default": True, "description": "Include one-click copy button."},
        ],
        "example": 'ui.code_block("pip install radui", language="bash", copyable=True)',
    },
    {
        "name": "kbd",
        "domain": "Typography & Code",
        "description": "Keyboard shortcut indicator styled as hardware keycaps.",
        "params": [],
        "example": 'ui.row(ui.text("Press"), ui.kbd("Ctrl", "K"), ui.text("for Command Palette"), gap=6)',
    },

    # 3. Action & Trigger Primitives (5)
    {
        "name": "button",
        "domain": "Action & Trigger",
        "description": "Interactive trigger button dispatching a registered RADUI server command.",
        "params": [
            {"name": "label", "type": "str", "default": "Execute Command", "description": "Button label text."},
            {"name": "variant", "type": "str", "default": "primary", "options": ["primary", "secondary", "outline", "ghost", "danger"], "description": "Visual style."},
            {"name": "size", "type": "str", "default": "md", "options": ["sm", "md", "lg"], "description": "Button size."},
            {"name": "disabled", "type": "bool", "default": False, "description": "Disabled state."},
        ],
        "example": 'ui.button("Deploy Cluster", command="cluster.deploy", variant="primary")',
    },
    {
        "name": "link",
        "domain": "Action & Trigger",
        "description": "Hyperlink strictly validated against secure http/https schemes to prevent XSS.",
        "params": [
            {"name": "label", "type": "str", "default": "View Documentation", "description": "Link anchor text."},
            {"name": "href", "type": "str", "default": "/getting-started", "description": "Target URL."},
            {"name": "external", "type": "bool", "default": False, "description": "Open in new window."},
        ],
        "example": 'ui.link("GitHub Repository", "https://github.com/flux-py/radui", external=True)',
    },
    {
        "name": "dropdown_menu",
        "domain": "Action & Trigger",
        "description": "Floating contextual menu revealing actions on trigger click.",
        "params": [
            {"name": "trigger_label", "type": "str", "default": "Actions", "description": "Trigger button text."},
        ],
        "example": 'ui.dropdown_menu("Export Options", [\n    ui.dropdown_menu_item("CSV Export", command="export.csv"),\n    ui.dropdown_menu_item("JSON Export", command="export.json"),\n])',
    },
    {
        "name": "dropdown_menu_item",
        "domain": "Action & Trigger",
        "description": "Action item within a dropdown menu supporting command dispatch or navigation.",
        "params": [
            {"name": "label", "type": "str", "default": "Delete Record", "description": "Item label."},
            {"name": "danger", "type": "bool", "default": False, "description": "Destructive item styling."},
        ],
        "example": 'ui.dropdown_menu_item("Purge Cache", command="cache.purge", danger=True)',
    },
    {
        "name": "theme_toggle",
        "domain": "Action & Trigger",
        "description": "Interactive theme switcher with dark/light mode transitions and localStorage persistence.",
        "params": [
            {"name": "label", "type": "str", "default": "Toggle Theme", "description": "Button label text."},
        ],
        "example": 'ui.theme_toggle("Toggle Theme")',
    },

    # 4. Form & Data Input Primitives (11)
    {
        "name": "form",
        "domain": "Form & Data Input",
        "description": "Declarative form container automatically injecting CSRF tokens and binding child inputs.",
        "params": [
            {"name": "command", "type": "str", "default": "form.submit", "description": "Target server command identifier."},
        ],
        "example": 'ui.form(\n    ui.input("Workspace Name", bind=s_name),\n    ui.button("Create", variant="primary"),\n    command="workspace.create",\n)',
    },
    {
        "name": "input",
        "domain": "Form & Data Input",
        "description": "Single-line text input bound to a reactive StateRef. Supports text, email, number, url.",
        "params": [
            {"name": "label", "type": "str", "default": "Search Query", "description": "Input field label."},
            {"name": "type", "type": "str", "default": "text", "options": ["text", "email", "password", "number", "url", "search"], "description": "HTML input type."},
            {"name": "placeholder", "type": "str", "default": "Enter search...", "description": "Placeholder text."},
        ],
        "example": 'ui.input("Email Address", bind=s_email, type="email", placeholder="developer@flux.py")',
    },
    {
        "name": "textarea",
        "domain": "Form & Data Input",
        "description": "Multi-line text entry field bound to a reactive StateRef.",
        "params": [
            {"name": "label", "type": "str", "default": "Description", "description": "Textarea label."},
            {"name": "rows", "type": "int", "default": 4, "description": "Visible row count."},
        ],
        "example": 'ui.textarea("Prompt Instructions", bind=s_prompt, rows=5)',
    },
    {
        "name": "checkbox",
        "domain": "Form & Data Input",
        "description": "Boolean toggle checkbox bound directly to a boolean StateRef.",
        "params": [
            {"name": "label", "type": "str", "default": "Enable SSE Compression", "description": "Checkbox label text."},
            {"name": "disabled", "type": "bool", "default": False, "description": "Disabled state."},
        ],
        "example": 'ui.checkbox("Enable Telemetry Tracing", bind=s_telemetry)',
    },
    {
        "name": "switch",
        "domain": "Form & Data Input",
        "description": "Hardware-styled toggle switch component bound to boolean reactive state.",
        "params": [
            {"name": "label", "type": "str", "default": "Auto Reconnect", "description": "Switch label."},
        ],
        "example": 'ui.switch("Maintenance Mode", bind=s_maintenance)',
    },
    {
        "name": "radio_group",
        "domain": "Form & Data Input",
        "description": "Mutually-exclusive radio selection list bound to a string StateRef.",
        "params": [
            {"name": "label", "type": "str", "default": "Storage Backend", "description": "Group label."},
        ],
        "example": 'ui.radio_group("Database Backend", bind=s_db, options=["sqlite", "postgres", "redis"])',
    },
    {
        "name": "select",
        "domain": "Form & Data Input",
        "description": "Single-choice dropdown select control supporting label-value option tuples.",
        "params": [
            {"name": "label", "type": "str", "default": "Environment Tier", "description": "Select label."},
            {"name": "placeholder", "type": "str", "default": "Choose option", "description": "Prompt text."},
        ],
        "example": 'ui.select("Cluster Region", bind=s_region, options=[("us-east-1", "US East"), ("eu-west-1", "EU West")])',
    },
    {
        "name": "slider",
        "domain": "Form & Data Input",
        "description": "Continuous or stepped numeric range input with live value readouts.",
        "params": [
            {"name": "label", "type": "str", "default": "Worker Pool Size", "description": "Slider label."},
            {"name": "min_value", "type": "float", "default": 1.0, "description": "Minimum value."},
            {"name": "max_value", "type": "float", "default": 32.0, "description": "Maximum value."},
            {"name": "step", "type": "float", "default": 1.0, "description": "Step interval."},
        ],
        "example": 'ui.slider("Concurrent Jobs", bind=s_concurrency, min_value=1, max_value=64, step=1)',
    },
    {
        "name": "date_picker",
        "domain": "Form & Data Input",
        "description": "Accessible calendar date picker input formatted to ISO-8601 (YYYY-MM-DD).",
        "params": [
            {"name": "label", "type": "str", "default": "Audit Start Date", "description": "Date input label."},
        ],
        "example": 'ui.date_picker("Deployment Date", bind=s_date)',
    },
    {
        "name": "time_picker",
        "domain": "Form & Data Input",
        "description": "Accessible time selection control formatted to 24-hour time (HH:MM).",
        "params": [
            {"name": "label", "type": "str", "default": "Backup Window", "description": "Time input label."},
        ],
        "example": 'ui.time_picker("Daily Backup Time", bind=s_time)',
    },
    {
        "name": "file_upload",
        "domain": "Form & Data Input",
        "description": "Drag-and-drop file upload zone with client-side size validation and file listing.",
        "params": [
            {"name": "command", "type": "str", "default": "file.upload", "description": "Server upload command."},
            {"name": "accept", "type": "str", "default": "*/*", "description": "Accepted MIME extensions."},
            {"name": "max_size_mb", "type": "int", "default": 10, "description": "Maximum file size limit."},
        ],
        "example": 'ui.file_upload(command="dataset.upload", accept=".csv,.json", max_size_mb=25)',
    },

    # 5. Feedback & Overlays (7)
    {
        "name": "modal",
        "domain": "Feedback & Overlays",
        "description": "Accessible dialog overlay featuring focus-trapping, Escape key dismissal, and backdrop handling.",
        "params": [
            {"name": "title", "type": "str", "default": "Confirm Cluster Restart", "description": "Modal header title."},
            {"name": "trigger_label", "type": "str", "default": "Open Modal", "description": "Trigger button text."},
        ],
        "example": 'ui.modal("Restart Server", ui.text("Are you sure you want to restart?"), trigger_label="Restart")',
    },
    {
        "name": "drawer",
        "domain": "Feedback & Overlays",
        "description": "Off-canvas sliding drawer panel supporting placements: left, right, top, bottom.",
        "params": [
            {"name": "title", "type": "str", "default": "Telemetry Details", "description": "Drawer title."},
            {"name": "placement", "type": "str", "default": "right", "options": ["right", "left", "top", "bottom"], "description": "Slide-in placement."},
        ],
        "example": 'ui.drawer("Node Inspector", ui.text("Detailed trace records"), trigger_label="Inspect")',
    },
    {
        "name": "popover",
        "domain": "Feedback & Overlays",
        "description": "Contextual floating popover bubble anchored to a trigger button.",
        "params": [
            {"name": "title", "type": "str", "default": "Idempotency Guarantee", "description": "Popover title."},
            {"name": "content", "type": "str", "default": "Monotonic fencing tokens reject stale leases.", "description": "Popover content."},
        ],
        "example": 'ui.popover("Lease Fencing", "Guarantees split-brain prevention under partitions.")',
    },
    {
        "name": "tooltip",
        "domain": "Feedback & Overlays",
        "description": "Lightweight hover/focus indicator providing descriptive text for buttons and icons.",
        "params": [
            {"name": "text", "type": "str", "default": "Copy snippet to clipboard", "description": "Tooltip content."},
        ],
        "example": 'ui.tooltip("Copy command", ui.button("Copy"))',
    },
    {
        "name": "toast",
        "domain": "Feedback & Overlays",
        "description": "Individual transient toast alert message. Variants: info, success, warning, danger.",
        "params": [
            {"name": "message", "type": "str", "default": "Configuration saved.", "description": "Alert message."},
            {"name": "variant", "type": "str", "default": "success", "options": ["info", "success", "warning", "danger"], "description": "Notification style."},
        ],
        "example": 'ui.toast("State synchronized successfully", variant="success")',
    },
    {
        "name": "toast_container",
        "domain": "Feedback & Overlays",
        "description": "Fixed viewport overlay positioning toast notifications.",
        "params": [
            {"name": "placement", "type": "str", "default": "top-right", "options": ["top-right", "top-left", "bottom-right", "bottom-left"], "description": "Screen anchor."},
        ],
        "example": 'ui.toast_container(ui.toast("Cache purged", variant="info"))',
    },
    {
        "name": "error_boundary",
        "domain": "Feedback & Overlays",
        "description": "Catches unhandled rendering exceptions in isolated subtrees without breaking surrounding page.",
        "params": [
            {"name": "fallback_message", "type": "str", "default": "Widget failed to render.", "description": "Graceful fallback notice."},
        ],
        "example": 'ui.error_boundary(failing_widget(), fallback_message="Live widget temporarily unavailable.")',
    },

    # 6. Navigation (5)
    {
        "name": "breadcrumb",
        "domain": "Navigation",
        "description": "Breadcrumb navigation bar indicating hierarchical path position.",
        "params": [],
        "example": 'ui.breadcrumb(\n    ui.breadcrumb_item("Home", href="/"),\n    ui.breadcrumb_item("Components", href="/components"),\n    ui.breadcrumb_item("Button", active=True),\n)',
    },
    {
        "name": "breadcrumb_item",
        "domain": "Navigation",
        "description": "Individual breadcrumb entry supporting hyperlinked routes or active leaf nodes.",
        "params": [
            {"name": "label", "type": "str", "default": "Components", "description": "Path segment label."},
            {"name": "active", "type": "bool", "default": False, "description": "Whether segment is current active leaf."},
        ],
        "example": 'ui.breadcrumb_item("Architecture", href="/architecture")',
    },
    {
        "name": "pagination",
        "domain": "Navigation",
        "description": "Page selector control with Previous, Next, and numeric page buttons dispatching commands.",
        "params": [
            {"name": "current_page", "type": "int", "default": 1, "description": "Active page index."},
            {"name": "total_pages", "type": "int", "default": 10, "description": "Total page count."},
            {"name": "command", "type": "str", "default": "page.change", "description": "Pagination command."},
        ],
        "example": 'ui.pagination(current_page=2, total_pages=8, command="records.page")',
    },
    {
        "name": "tabs",
        "domain": "Navigation",
        "description": "Tabbed container switching visible child panels based on active tab selection.",
        "params": [
            {"name": "active_index", "type": "int", "default": 0, "description": "Initially selected tab."},
        ],
        "example": 'ui.tabs(\n    ui.tab_item("Python API", ui.code_block("import radui as ui")),\n    ui.tab_item("CLI", ui.code_block("radui run")),\n)',
    },
    {
        "name": "tab_item",
        "domain": "Navigation",
        "description": "Single tab section holding child components associated with a tab header.",
        "params": [
            {"name": "label", "type": "str", "default": "Overview", "description": "Tab header text."},
        ],
        "example": 'ui.tab_item("Benchmarks", ui.text("AST Construction: 0.039 ms"))',
    },

    # 7. Data Display & Tables (5)
    {
        "name": "table",
        "domain": "Data Display & Tables",
        "description": "Responsive data table with striped alternating rows and hover highlighting.",
        "params": [
            {"name": "striped", "type": "bool", "default": True, "description": "Zebra striping style."},
        ],
        "example": 'ui.table(\n    headers=["Worker", "Status", "Latency"],\n    rows=[["worker-1", "ACTIVE", "0.039ms"], ["worker-2", "ACTIVE", "0.042ms"]],\n)',
    },
    {
        "name": "data_grid",
        "domain": "Data Display & Tables",
        "description": "Interactive data grid featuring instant search filtering, column sorting, and pagination.",
        "params": [
            {"name": "searchable", "type": "bool", "default": True, "description": "Include client-side search box."},
            {"name": "sortable", "type": "bool", "default": True, "description": "Enable column header sorting."},
            {"name": "page_size", "type": "int", "default": 10, "description": "Items per page."},
        ],
        "example": 'ui.data_grid(\n    headers=["Component", "Category", "AST Overhead"],\n    rows=[["button", "Action", "0.015ms"], ["data_grid", "Data", "0.082ms"]],\n    searchable=True,\n)',
    },
    {
        "name": "virtual_list",
        "domain": "Data Display & Tables",
        "description": "Windowed virtualization list rendering massive datasets via CSS translateY spacers.",
        "params": [
            {"name": "item_height", "type": "int", "default": 40, "description": "Fixed height of each item in pixels."},
            {"name": "viewport_height", "type": "int", "default": 400, "description": "Scrollable viewport height."},
        ],
        "example": 'ui.virtual_list(items=[f"Log Entry #{i}" for i in range(10000)], item_height=36, viewport_height=300)',
    },
    {
        "name": "metric_card",
        "domain": "Data Display & Tables",
        "description": "KPI metric card with formatted values, comparison deltas, and trend status indicators.",
        "params": [
            {"name": "title", "type": "str", "default": "AST Render Latency", "description": "Metric title."},
            {"name": "value", "type": "str", "default": "0.039 ms", "description": "Metric value."},
            {"name": "delta", "type": "str", "default": "-18% vs v0.9", "description": "Comparison delta."},
        ],
        "example": 'ui.metric_card("Reconciliation Time", "0.168 ms", delta="-42% latency")',
    },
    {
        "name": "plot",
        "domain": "Data Display & Tables",
        "description": "Zero-dependency pure SVG chart generator rendering bar, line, and scatter series with zero JS.",
        "params": [
            {"name": "plot_type", "type": "str", "default": "bar", "options": ["bar", "line", "scatter"], "description": "Chart visualization style."},
            {"name": "height", "type": "int", "default": 240, "description": "SVG chart height in pixels."},
        ],
        "example": 'ui.plot(data=[{"x": "T1", "y": 0.039}, {"x": "T2", "y": 0.038}, {"x": "T3", "y": 3.037}], plot_type="bar")',
    },

    # 8. Indicators & Avatars (8)
    {
        "name": "badge",
        "domain": "Indicators & Avatars",
        "description": "Compact status pill badge. Variants: primary, secondary, success, warning, danger.",
        "params": [
            {"name": "label", "type": "str", "default": "Operational", "description": "Badge label text."},
            {"name": "variant", "type": "str", "default": "success", "options": ["primary", "secondary", "success", "warning", "danger"], "description": "Badge style."},
        ],
        "example": 'ui.badge("v1.0.0 Production", variant="primary")',
    },
    {
        "name": "tag",
        "domain": "Indicators & Avatars",
        "description": "Categorization tag element with optional dismiss button dispatching a command.",
        "params": [
            {"name": "label", "type": "str", "default": "Reactive", "description": "Tag label."},
            {"name": "removable", "type": "bool", "default": False, "description": "Display dismiss trigger."},
        ],
        "example": 'ui.tag("Python 3.12", variant="secondary")',
    },
    {
        "name": "progress_bar",
        "domain": "Indicators & Avatars",
        "description": "Horizontal progress bar indicator with optional striping and animations.",
        "params": [
            {"name": "value", "type": "float", "default": 75.0, "description": "Current progress value."},
            {"name": "max_value", "type": "float", "default": 100.0, "description": "Maximum value."},
            {"name": "variant", "type": "str", "default": "primary", "options": ["primary", "success", "warning", "danger"], "description": "Color theme."},
        ],
        "example": 'ui.progress_bar(value=85.0, variant="success")',
    },
    {
        "name": "progress_circle",
        "domain": "Indicators & Avatars",
        "description": "Radial SVG progress ring with centered percentage readout.",
        "params": [
            {"name": "value", "type": "float", "default": 92.0, "description": "Percentage value (0-100)."},
            {"name": "size", "type": "int", "default": 64, "description": "Diameter in pixels."},
        ],
        "example": 'ui.progress_circle(value=98.5, size=72, variant="primary")',
    },
    {
        "name": "avatar",
        "domain": "Indicators & Avatars",
        "description": "User profile avatar displaying image source or automatically derived initials.",
        "params": [
            {"name": "name", "type": "str", "default": "Alex Mercer", "description": "User display name."},
            {"name": "size", "type": "str", "default": "md", "options": ["sm", "md", "lg"], "description": "Avatar size."},
            {"name": "status", "type": "str", "default": "online", "options": ["online", "busy", "offline"], "description": "Status indicator dot."},
        ],
        "example": 'ui.avatar(name="Core Maintainer", size="md", status="online")',
    },
    {
        "name": "avatar_group",
        "domain": "Indicators & Avatars",
        "description": "Overlapping avatar cluster automatically truncating excess users into an +N overflow badge.",
        "params": [
            {"name": "max_visible", "type": "int", "default": 3, "description": "Maximum visible avatars."},
        ],
        "example": 'ui.avatar_group(\n    ui.avatar(name="Ada Lovelace"),\n    ui.avatar(name="Alan Turing"),\n    ui.avatar(name="Grace Hopper"),\n    ui.avatar(name="Linus Torvalds"),\n    max_visible=3,\n)',
    },
    {
        "name": "skeleton",
        "domain": "Indicators & Avatars",
        "description": "Shimmering placeholder loader matching content shape (rect, circle, text).",
        "params": [
            {"name": "shape", "type": "str", "default": "rect", "options": ["rect", "circle", "text"], "description": "Geometric shape."},
            {"name": "height", "type": "str", "default": "24px", "description": "Placeholder height."},
        ],
        "example": 'ui.skeleton(shape="rect", width="100%", height="48px")',
    },
    {
        "name": "empty_state",
        "domain": "Indicators & Avatars",
        "description": "Zero-state presentation screen with heading, explanation, and action button.",
        "params": [
            {"name": "title", "type": "str", "default": "No Active Clusters", "description": "Zero-state title."},
            {"name": "description", "type": "str", "default": "Deploy a new worker pool to view telemetry.", "description": "Explanation text."},
        ],
        "example": 'ui.empty_state("No Telemetry Found", "Trigger command to populate event logs.", action=ui.button("Start Telemetry"))',
    },

    # 9. Diagrams & Trees (2)
    {
        "name": "diagram",
        "domain": "Diagrams & Trees",
        "description": "Pure SVG architecture diagram and flowchart canvas supporting interactive click commands.",
        "params": [
            {"name": "width", "type": "str", "default": "100%", "description": "Canvas width."},
            {"name": "height", "type": "int", "default": 320, "description": "Canvas height in pixels."},
        ],
        "example": 'ui.diagram(\n    nodes=[\n        ui.diagram_node("n1", "Client DOM", 50, 100),\n        ui.diagram_node("n2", "ASGI Engine", 250, 100),\n    ],\n    edges=[ui.diagram_edge("n1", "n2", label="POST /command")],\n)',
    },
    {
        "name": "tree_view",
        "domain": "Diagrams & Trees",
        "description": "Hierarchical tree explorer with collapsible branches, expandable carets, and selection listeners.",
        "params": [],
        "example": 'ui.tree_view([\n    ui.tree_node("radui", "radui/", children=[\n        ui.tree_node("core", "core/"),\n        ui.tree_node("state", "state/"),\n    ], expanded=True),\n])',
    },

    # 10. AI Agent & Workflow (8)
    {
        "name": "chat_view",
        "domain": "AI Agent & Workflow",
        "description": "Conversation message scrollbox featuring auto-scroll, message bubbles, and typing indicators.",
        "params": [
            {"name": "height", "type": "str", "default": "400px", "description": "Chat window height."},
        ],
        "example": 'ui.chat_view(\n    ui.chat_message("Hello from RADUI AI agent!", sender="assistant"),\n    height="400px",\n)',
    },
    {
        "name": "chat_message",
        "domain": "AI Agent & Workflow",
        "description": "Individual chat message bubble supporting markdown, code formatting, and metadata.",
        "params": [
            {"name": "content", "type": "str", "default": "RADUI executes server-driven reactive state updates.", "description": "Message body."},
            {"name": "sender", "type": "str", "default": "assistant", "options": ["assistant", "user", "system"], "description": "Sender role."},
        ],
        "example": 'ui.chat_message("Can you explain transactional outboxes?", sender="user")',
    },
    {
        "name": "chat_input",
        "domain": "AI Agent & Workflow",
        "description": "Conversational input box supporting Enter-to-submit and file attachments.",
        "params": [
            {"name": "command", "type": "str", "default": "agent.send", "description": "Target send command."},
            {"name": "placeholder", "type": "str", "default": "Ask a question...", "description": "Placeholder text."},
        ],
        "example": 'ui.chat_input(command="agent.chat", placeholder="Ask RADUI agent...")',
    },
    {
        "name": "streaming_text",
        "domain": "AI Agent & Workflow",
        "description": "Real-time token stream text box with animated blinking cursor.",
        "params": [
            {"name": "content", "type": "str", "default": "Streaming response token chunks over SSE...", "description": "Active streamed text."},
            {"name": "is_streaming", "type": "bool", "default": True, "description": "Display cursor animation."},
        ],
        "example": 'ui.streaming_text("Tokens arriving in 0.007ms chunks...", is_streaming=True)',
    },
    {
        "name": "action_card",
        "domain": "AI Agent & Workflow",
        "description": "Human-in-the-loop (HITL) card enabling users to authorize or reject agent tool executions.",
        "params": [
            {"name": "title", "type": "str", "default": "Execute Database Query?", "description": "Action card title."},
            {"name": "description", "type": "str", "default": "Agent requests permission to run analytics aggregation.", "description": "Action explanation."},
        ],
        "example": 'ui.action_card(\n    title="Authorize Tool Dispatch?",\n    description="Execute query on production DB.",\n    confirm_command="agent.approve",\n    cancel_command="agent.reject",\n)',
    },
    {
        "name": "step_timeline",
        "domain": "AI Agent & Workflow",
        "description": "Multi-step execution audit timeline displaying tool invocations, progress state, and latency.",
        "params": [],
        "example": 'ui.step_timeline([\n    {"title": "Request Validated", "status": "completed", "latency": "0.12ms"},\n    {"title": "State Invalidation", "status": "completed", "latency": "0.168ms"},\n    {"title": "SSE Patch Emitted", "status": "active", "latency": "0.007ms"},\n])',
    },
    {
        "name": "generative_slot",
        "domain": "AI Agent & Workflow",
        "description": "Dynamic DOM container allowing backend AI agents to swap or generate UI component trees.",
        "params": [
            {"name": "id", "type": "str", "default": "agent_slot", "description": "Unique slot DOM identifier."},
        ],
        "example": 'ui.generative_slot(id="dynamic_ai_slot", component=ui.card(ui.text("Agent generated view")))',
    },
    {
        "name": "job_panel",
        "domain": "AI Agent & Workflow",
        "description": "Real-time background job monitor with progress bar, state badge, and cancellation trigger.",
        "params": [
            {"name": "job_id", "type": "str", "default": "job-101", "description": "Monitored background job ID."},
        ],
        "example": 'ui.job_panel(job_id="export-daily-kpis")',
    },
]

assert len(COMPONENTS) == 68, f"Expected 68 components, got {len(COMPONENTS)}"


# =========================================================================
# 2. CLI SUBCOMMANDS CATALOG (All 45 Subcommands)
# =========================================================================

CLI_COMMANDS: list[dict[str, str]] = [
    # Serving & Runtime (6)
    {"cmd": "run", "domain": "Serving & Runtime", "syntax": "radui run [app.py] [--port 3000]", "description": "Start standard ASGI production server."},
    {"cmd": "dev", "domain": "Serving & Runtime", "syntax": "radui dev [app.py] [--port 3000] [--open]", "description": "Start development server with live file watching and reload."},
    {"cmd": "serve", "domain": "Serving & Runtime", "syntax": "radui serve [app.py] [--workers 4]", "description": "Start multi-worker production cluster with process supervisor."},
    {"cmd": "demo", "domain": "Serving & Runtime", "syntax": "radui demo", "description": "Launch the interactive RADUI Guided Tour on port 3000."},
    {"cmd": "stop", "domain": "Serving & Runtime", "syntax": "radui stop [--port 3000]", "description": "Terminate running RADUI server processes listening on port."},
    {"cmd": "restart", "domain": "Serving & Runtime", "syntax": "radui restart [app.py]", "description": "Gracefully restart a running RADUI application instance."},

    # Project Scaffolding & Setup (6)
    {"cmd": "new", "domain": "Scaffolding & Setup", "syntax": "radui new <dir> [--template architecture|dashboard|agent|basic]", "description": "Generate a new starter project directory."},
    {"cmd": "init", "domain": "Scaffolding & Setup", "syntax": "radui init", "description": "Initialize RADUI configuration in existing directory."},
    {"cmd": "add", "domain": "Scaffolding & Setup", "syntax": "radui add <module>", "description": "Install optional capability modules (mcp, server, telemetry)."},
    {"cmd": "upgrade", "domain": "Scaffolding & Setup", "syntax": "radui upgrade", "description": "Upgrade RADUI and dependencies to latest stable release."},
    {"cmd": "version", "domain": "Scaffolding & Setup", "syntax": "radui version", "description": "Print framework version and Python runtime release."},
    {"cmd": "info", "domain": "Scaffolding & Setup", "syntax": "radui info", "description": "Display OS, ASGI server, and environment configuration."},

    # Quality, Auditing & Diagnostics (7)
    {"cmd": "check", "domain": "Quality & Diagnostics", "syntax": "radui check [app.py]", "description": "Execute static pre-flight component and route linting."},
    {"cmd": "audit", "domain": "Quality & Diagnostics", "syntax": "radui audit [app.py] --a11y", "description": "Run automated static accessibility diagnostics (WCAG 2.2 AA)."},
    {"cmd": "test", "domain": "Quality & Diagnostics", "syntax": "radui test", "description": "Execute application pytest test suite."},
    {"cmd": "lint", "domain": "Quality & Diagnostics", "syntax": "radui lint [app.py]", "description": "Validate Application IR schemas and component bindings."},
    {"cmd": "validate", "domain": "Quality & Diagnostics", "syntax": "radui validate [app.py]", "description": "Verify state context bindings and command identifiers."},
    {"cmd": "security", "domain": "Quality & Diagnostics", "syntax": "radui security [app.py]", "description": "Audit cookie flags, CSRF tokens, and secret persistence."},
    {"cmd": "doctor", "domain": "Quality & Diagnostics", "syntax": "radui doctor", "description": "Diagnose local system health, port availability, and packages."},

    # Build & Distribution (6)
    {"cmd": "build", "domain": "Build & Distribution", "syntax": "radui build [app.py]", "description": "Compile and package production distribution artifacts into ./dist."},
    {"cmd": "bundle", "domain": "Build & Distribution", "syntax": "radui bundle [app.py]", "description": "Bundle application code and local static assets."},
    {"cmd": "export", "domain": "Build & Distribution", "syntax": "radui export [app.py] --static", "description": "Pre-render pages into standalone zero-server HTML document bundles."},
    {"cmd": "assets", "domain": "Build & Distribution", "syntax": "radui assets", "description": "Inspect embedded static assets footprint (~37.6 KB raw / ~9.6 KB gzip)."},
    {"cmd": "clean", "domain": "Build & Distribution", "syntax": "radui clean", "description": "Remove generated artifacts, test caches, and __pycache__."},
    {"cmd": "deploy", "domain": "Build & Distribution", "syntax": "radui deploy", "description": "Generate containerized Dockerfiles and deployment manifests."},

    # Inspection, Telemetry & Profiling (10)
    {"cmd": "routes", "domain": "Inspection & Telemetry", "syntax": "radui routes [app.py]", "description": "List all registered routes, command handlers, and background jobs."},
    {"cmd": "components", "domain": "Inspection & Telemetry", "syntax": "radui components", "description": "Display catalog of all 68 built-in components grouped by domain."},
    {"cmd": "tree", "domain": "Inspection & Telemetry", "syntax": "radui tree [app.py]", "description": "Render visual ASCII tree of route and component hierarchies."},
    {"cmd": "inspect", "domain": "Inspection & Telemetry", "syntax": "radui inspect", "description": "Open runtime telemetry inspector in browser (Ctrl+Shift+I)."},
    {"cmd": "schema", "domain": "Inspection & Telemetry", "syntax": "radui schema", "description": "Output Application IR JSON schema definition."},
    {"cmd": "metrics", "domain": "Inspection & Telemetry", "syntax": "radui metrics [--benchmark]", "description": "Display real-time throughput, latency, or execute 6-tier benchmarks."},
    {"cmd": "telemetry", "domain": "Inspection & Telemetry", "syntax": "radui telemetry", "description": "Export runtime telemetry spans and execution traces to OTLP."},
    {"cmd": "profile", "domain": "Inspection & Telemetry", "syntax": "radui profile", "description": "Profile component rendering and command dispatch latencies."},
    {"cmd": "health", "domain": "Inspection & Telemetry", "syntax": "radui health", "description": "Execute runtime readiness and liveness health checks."},
    {"cmd": "events", "domain": "Inspection & Telemetry", "syntax": "radui events", "description": "Monitor live EventBroker SSE stream records and sequences."},

    # State & Background Subsystems (4)
    {"cmd": "state", "domain": "State & Jobs", "syntax": "radui state", "description": "Inspect active reactive state scopes and registered keys."},
    {"cmd": "jobs", "domain": "State & Jobs", "syntax": "radui jobs", "description": "Inspect background job queue statuses and active leases."},
    {"cmd": "config", "domain": "State & Jobs", "syntax": "radui config", "description": "Inspect and validate active application configuration settings."},
    {"cmd": "secrets", "domain": "State & Jobs", "syntax": "radui secrets", "description": "Audit environment variables and session secret configurations."},

    # AI & Protocols (6)
    {"cmd": "agent", "domain": "AI & Protocols", "syntax": "radui agent", "description": "Inspect registered AI agent adapters and tools."},
    {"cmd": "mcp", "domain": "AI & Protocols", "syntax": "radui mcp", "description": "Inspect Model Context Protocol tools and schemas."},
    {"cmd": "protocols", "domain": "AI & Protocols", "syntax": "radui protocols", "description": "Audit supported frontend protocols (SSE, A2UI, AG-UI)."},
    {"cmd": "a2ui", "domain": "AI & Protocols", "syntax": "radui a2ui", "description": "Validate and test Agent-to-UI component conversion pipelines."},
    {"cmd": "agui", "domain": "AI & Protocols", "syntax": "radui agui", "description": "Inspect and stream AG-UI event journal sequences."},
    {"cmd": "tools", "domain": "AI & Protocols", "syntax": "radui tools", "description": "List all registered tool descriptors available for agent dispatch."},
]

assert len(CLI_COMMANDS) == 45, f"Expected 45 CLI commands, got {len(CLI_COMMANDS)}"


# =========================================================================
# 3. ARCHITECTURE DECISION RECORDS (12 ADRs)
# =========================================================================

ADRS: list[dict[str, str]] = [
    {
        "id": "ADR-001",
        "title": "Monotonic Fencing Tokens & Resource-Level Fencing",
        "scope": "Jobs & State Leasing",
        "invariant": "Eliminates split-brain overwrites with dual-condition fence tokens.",
        "path": "docs/adr/ADR-001-monotonic-fencing-tokens.md",
    },
    {
        "id": "ADR-002",
        "title": "Transactional Outbox Pattern & Forward Compensation",
        "scope": "Distributed Side Effects",
        "invariant": "Guarantees at-least-once external delivery with local database atomicity.",
        "path": "docs/adr/ADR-002-transactional-outbox.md",
    },
    {
        "id": "ADR-003",
        "title": "High-Watermark Event Replay Architecture",
        "scope": "SSE Real-Time Broker",
        "invariant": "Guarantees ordered reconnect delivery with cursor validation and backpressure shedding.",
        "path": "docs/adr/ADR-003-high-watermark-sse-replay.md",
    },
    {
        "id": "ADR-004",
        "title": "Standardizing Native PostgreSQL on psycopg 3",
        "scope": "Database Adapters",
        "invariant": "Native async connection pooling, row-level locks, and fail-fast timeouts.",
        "path": "docs/adr/ADR-004-psycopg3-native-postgresql.md",
    },
    {
        "id": "ADR-005",
        "title": "Multi-Tenant Logical Namespace Isolation & Database RLS",
        "scope": "Multi-Tenancy Security",
        "invariant": "Cryptographically segregated tenant namespaces with enforced PostgreSQL RLS.",
        "path": "docs/adr/ADR-005-multi-tenant-key-isolation.md",
    },
    {
        "id": "ADR-006",
        "title": "5-State Client Mutation Lifecycle & IndexedDB Queue",
        "scope": "Offline & Resiliency",
        "invariant": "Resilient offline action queuing and cross-tab Web Locks replay coordination.",
        "path": "docs/adr/ADR-006-five-state-client-mutation-lifecycle.md",
    },
    {
        "id": "ADR-007",
        "title": "Distributed Consistency & Failure Semantics",
        "scope": "Cluster Failover",
        "invariant": "Subsystem failure matrix and fail-closed split-brain prevention across nodes.",
        "path": "docs/adr/ADR-007-distributed-consistency-failure-semantics.md",
    },
    {
        "id": "ADR-008",
        "title": "Reactive State Transaction Semantics & Batching",
        "scope": "Reactive State Engine",
        "invariant": "ACID-like memory rollbacks for ctx.transaction() and consolidated batching.",
        "path": "docs/adr/ADR-008-reactive-state-transaction-semantics.md",
    },
    {
        "id": "ADR-009",
        "title": "Query Cache Consistency & Singleflight Invalidation",
        "scope": "Data SWR Layer",
        "invariant": "Lock-based concurrent query deduplication and generation checking.",
        "path": "docs/adr/ADR-009-query-cache-consistency-invalidation.md",
    },
    {
        "id": "ADR-010",
        "title": "Framework Security Architecture & Threat Model",
        "scope": "Security Hardening",
        "invariant": "Hardened CSP policies, CSRF validation, and RBAC security boundaries.",
        "path": "docs/adr/ADR-010-framework-security-threat-model.md",
    },
    {
        "id": "ADR-011",
        "title": "Background Job Execution & Distributed Leasing",
        "scope": "Job Runner",
        "invariant": "Monotonic heartbeat fencing, worker crash recovery, and live telemetry.",
        "path": "docs/adr/ADR-011-background-job-execution-guarantees.md",
    },
    {
        "id": "ADR-012",
        "title": "Protocol Compatibility & Wire Versioning",
        "scope": "Protocol Specs",
        "invariant": "Schema evolution rules for Application IR, A2UI, and SSE stream contracts.",
        "path": "docs/adr/ADR-012-protocol-compatibility-versioning.md",
    },
]

assert len(ADRS) == 12, f"Expected 12 ADRs, got {len(ADRS)}"
