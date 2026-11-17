# RadUI Native Web Components Interoperability (M2.2)

RadUI M2.2 integrates standards-compliant Custom Elements (`customElements.define`) and Shadow DOM (`open`, `closed`, `none`) with Python components, reactive commands, resumability, and SPA navigation.

## 1. Python API

- `@app.web_component(tag_name, *, shadow_mode="open", observed_attributes=(), events=(), styles="", template_html="")`
- `gx.custom_element(tag_name, *children, props=None, shadow_mode="open", shadow_styles="", event_commands=None, resumable=False)`

## 2. Shadow DOM, Styling & Secure Event Bridge

- Inherits RadUI theme CSS custom properties (`--gx-primary`, `--gx-surface`, etc.) cleanly through Shadow DOM boundaries without forcing Shadow DOM onto ordinary RadUI components.
- Maps allowlisted Custom DOM Events (`event_commands={"rating-change": "rating.save"}`) to CSRF-protected `POST /_gx/commands/{id}` dispatches, rejecting prototype-pollution keys (`__proto__`, `constructor`, `prototype`) in event detail payloads.
- Automatically upgrades newly inserted Custom Elements during `RadUINavigator` SPA transitions and tears down listeners on `disconnectedCallback`.
