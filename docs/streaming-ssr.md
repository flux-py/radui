# RadUI Progressive & Streaming SSR (M2.3)

RadUI M2.3 extends `HTMLRenderer` and ASGI routing with Marko-inspired progressive out-of-order streaming SSR via `gx.suspense(...)` and `@app.page(..., stream=True)`.

## 1. API

```python
@app.page("/dashboard", stream=True, ssg=False)
def dashboard():
    return gx.column(
        gx.heading("Dashboard"),
        gx.suspense(
            load_metrics,
            fallback=gx.text("Loading metrics..."),
            error_fallback=gx.text("Metrics unavailable"),
            timeout_s=3.0,
        ),
    )
```

## 2. Streaming Protocol & Security

- **Immediate Shell:** Sends `<head>`, CSS, `CLIENT_JS`, and synchronous fallback shells immediately (`StreamingResponse`).
- **Out-of-Order Completion:** Async boundaries resolve concurrently via `asyncio.as_completed`; faster boundaries render first regardless of document order.
- **Zero-Eval Nonce-Verified Replacement:** Streamed chunks emit `<template data-gx-stream-target="..." data-gx-stream-nonce="...">` (no inline `<script>`). `RadUIStream` verifies the per-request `gx-stream-nonce` `<meta>` tag before swapping the DOM and synchronizing `RadUIInteractions`, `RadUIResumability`, `RadUIWebComponents`, and `Motion`.
- **Backpressure & Cancellation:** Client disconnects cancel all pending boundary tasks immediately (`finally` cleanup).
- **SSG Compatibility:** Static builds (`radui build`) render `suspense` boundaries deterministically using their fallback content.
