# RadUI Native SPA Navigation Engine (M1.9 / M1.9.1)

RadUI provides native client-side navigation integrated with Python server routing, `@app.layout(...)`, route authorization, CSRF protection, and `RadUIInteractions`.

## 1. Python Routing & Link API

```python
import radui as gx

@app.layout("/")
def shell(outlet):
    return gx.column(
        gx.row(
            gx.link("Home", "/"),
            gx.link("Users", "/users/42", prefetch="viewport"),
            gx.link("External / Full Reload", "/legacy", spa=False),
        ),
        outlet,
    )

@app.page(
    "/users/{user_id}",
    title="User Profile",
    loading=lambda: gx.text("Loading profile..."),
    error_boundary=lambda exc: gx.text(f"Error: {exc}"),
    guard=lambda req: True,
)
def user_profile(user_id: str):
    return gx.heading(f"User {user_id}")
```

### Link Options (`gx.link`)
- `prefetch`: `"hover"` (default, triggers on `pointerover`/`focusin`), `"viewport"` (`IntersectionObserver`), `"none"`, or `"auto"`.
- `spa`: `True` (default) or `False` (forces standard full browser reload).
- `replace`: `False` (default) or `True` (uses `history.replaceState`).
- `scroll`: `True` (default) or `False` (suppresses auto-scroll to top).

## 2. Client Runtime API (`window.RadUINavigator`)

- `RadUINavigator.navigate(url, { replace, scroll })`: Programmatic SPA transition.
- `RadUINavigator.prefetch(url)`: Preloads `/_gx/navigate?to=...` into the 16-entry / 15s TTL cache.
- `RadUINavigator.beforeEach((to, from) => boolean | string | Promise<...>)`: Register a client navigation guard (returns `unsubscribe()`). Returning `false` cancels; returning a string path redirects (capped at 4 hops to prevent redirect loops).
- `RadUINavigator.afterEach((to, from, data) => void)`: Post-navigation hook.
- `RadUINavigator.clearCache()`: Clears cached route responses.

## 3. Nested Layout Persistence & Trade-offs

- **Preserved Across Transitions:** `CLIENT_JS`, `<head>` styles, `EventSource` SSE stream, `RadUINavigator` guards/cache, and `window` state remain live without full page reloads.
- **Replaced Subtree (`[data-gx-root]`):** Server-rendered HTML for `[data-gx-root]` (including `@app.layout(...)` wrappers) is swapped cleanly so layouts that compute active nav states or user-dependent UI on the server remain 100% consistent without client-side VDOM diffing. Removed DOM nodes' `WeakMap` state is automatically garbage-collected.

## 4. Security, Accessibility & Performance

- **Security:** `GET /_gx/navigate` validates same-origin relative paths (rejecting `//` and external URLs), enforces `require_auth`/`require_role`/`require_permission` and `page.guard`, escapes all user text via `HTMLRenderer`, updates `meta[name="gx-csrf"]` and `meta[name="gx-view"]`, and invalidates the prefetch cache on `401`/`403` or `auth_key` changes.
- **Accessibility:** Sets `aria-busy="true"` while loading, moves focus to the target `h1` / `[data-gx-autofocus]` / `[role='main']`, announces route changes via `#gx-live-region`, restores `scrollY` on `popstate`, and honors `prefers-reduced-motion`.
- **Measured Performance (`CLIENT_JS` + Chrome CDP):**
  - `CLIENT_JS`: `79,995 B` (`78.12 KiB`) raw, `18,607 B` (`18.17 KiB`) gzip (level 9; Brotli not measured — `brotli` package not installed).
  - Uncached SPA navigation: `p50 = 6.300 ms`, `p95 = 10.700 ms`.
  - Prefetched SPA navigation: `p50 = 0.800 ms`, `p95 = 1.200 ms`.
