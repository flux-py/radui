# ADR-018: Progressive and Streaming Server-Side Rendering (M2.3)

- **Status:** Accepted (M2.3)
- **Context:** Large pages with slow async data dependencies previously blocked TTFB until the slowest component finished rendering.
- **Decision:** Add `Suspense` / `gx.suspense(...)`, `radui/streaming/engine.py` (`stream_page_html`), `@app.page(..., stream=True)`, and `window.RadUIStream` in `CLIENT_JS` using nonce-verified `<template>` chunk replacement without inline `<script>` tags.
- **Consequences:** Initial HTML shells flush immediately, out-of-order boundaries complete concurrently with per-boundary timeouts and error fallbacks, client disconnects cancel pending tasks, and synchronous/SSG rendering remains deterministic.
