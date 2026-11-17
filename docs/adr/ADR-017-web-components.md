# ADR-017: Native Web Components Interoperability (M2.2)

- **Status:** Accepted (M2.2)
- **Context:** Applications need to embed standards-based Custom Elements (with open/closed Shadow DOM) inside RadUI and embed RadUI views in external HTML applications (`<radui-view>`).
- **Decision:** Add `radui/web_components/` (`WebComponentSpec`), `CustomElement` / `gx.custom_element(...)`, `@app.web_component(...)`, and `window.RadUIWebComponents` in `CLIENT_JS` with declarative `<slot>` projection, `observedAttributes`, `disconnectedCallback` cleanup, and CSRF-protected custom event command dispatch.
- **Consequences:** Custom Elements participate natively in SSR, M2.0 resumability, and M1.9 SPA navigation without forcing Shadow DOM on standard RadUI components.
