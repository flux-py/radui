# RadUI Integration Guide

This guide documents how to integrate RadUI into existing backend frameworks, frontend applications, and database/storage infrastructures using verified RadUI APIs.

## 1. Integration Architecture & Support Matrix

```mermaid
flowchart LR
    Proxy["Nginx / Envoy / ASGI Router"] -->|"/api/* (REST/GraphQL)"| Backend["Flask / Django / Spring Boot / FastAPI"]
    Proxy -->|"/ui/* or /* (SSR + SSE + SPA)"| RadUI["RadUI ASGI Runtime"]
    React["React / Next.js Host"] -->|"<radui-view> (/_gx/embed.js)"| RadUI
    RadUI -->|"Native Backends"| NativeDB["SQLite / PostgreSQL / Redis"]
    RadUI -->|"Custom @app.command / ui.query"| ExternalDB["MongoDB / CouchDB / External APIs"]
```

| Target | Category | What RadUI Handles Internally | What Developers Configure |
|---|---|---|---|
| **FastAPI / Starlette** | Native ASGI | SSR, SSE, SPA nav, CSRF, commands | `api.mount("/ui", radui_app.asgi())` |
| **Flask** | Adapter (WSGI->ASGI) | UI rendering, commands, SSE | `WSGIMiddleware(flask_app)` or side-by-side reverse proxy |
| **Django** | Adapter (ASGI / ORM) | UI rendering, thread-safe sync commands | ASGI route split + `user_id_resolver` + ORM calls |
| **Spring Boot** | Custom HTTP / Proxy | UI shell, SSE patches, CSRF | Nginx/Envoy route split + `httpx` REST calls + `user_id_resolver` |
| **React / Next.js** | Embed / Micro-Frontend | `<radui-view>` (`/_gx/embed.js`) or Web Components | Script tag or proxy route split |
| **SQLite** | Native Built-in | `SQLiteStateBackend`, `SQLiteJobBackend`, `SQLiteIdempotencyBackend` | Pass DB path |
| **PostgreSQL** | Native Built-in | `PostgreSQLStateBackend` (`psycopg` 3 + RLS) | Pass connection DSN |
| **Redis** | Native Built-in | `RedisStateBackend`, `RedisEventBackend`, `RedisJobBackend`, `RedisSSEGovernance` | Pass `redis_url` |
| **MongoDB** | Custom App Layer | `ui.query()` SWR cache + `@app.command` dispatch | `pymongo`/`motor` CRUD + `ui.invalidate_query()` |
| **Apache CouchDB** | Custom HTTP / `_changes` | `ui.query()` SWR cache + `app.notify()` | `httpx` REST CRUD + `_changes` listener |

---

## 2. Backend Frameworks

### FastAPI (Native ASGI Mount)

```python
from fastapi import FastAPI
import radui as ui

api = FastAPI()
radui_app = ui.App("EmbeddedUI")

@radui_app.page("/")
def ui_home():
    return ui.heading("Served from RadUI inside FastAPI")

@api.get("/api/health")
def api_health():
    return {"ok": True}

api.mount("/ui", radui_app.asgi())
```

### Flask (WSGI Adapter or Side-by-Side Reverse Proxy)

```python
from flask import Flask, jsonify
from a2wsgi import WSGIMiddleware
from starlette.applications import Starlette
from starlette.routing import Mount
import radui as ui

flask_app = Flask(__name__)

@flask_app.get("/api/orders")
def list_orders():
    return jsonify([{"id": 1, "status": "paid"}])

radui_app = ui.App("FlaskBridge")
app = Starlette(routes=[
    Mount("/api", app=WSGIMiddleware(flask_app)),
    Mount("/", app=radui_app.asgi()),
])
```

### Django (ASGI Composition & ORM Commands)

```python
import radui as ui

def resolve_django_user(request):
    return request.headers.get("x-authenticated-user")

radui_app = ui.App("DjangoUI", user_id_resolver=resolve_django_user)

@radui_app.command("invoice.mark_paid")
def mark_paid(ctx: ui.CommandContext):
    # Synchronous @app.command handlers run safely in anyio worker threads
    inv_id = ctx.form_data.get("invoice_id")
    # Invoice.objects.filter(id=inv_id).update(status="paid")
    radui_app.notify(f"Invoice {inv_id} marked paid", variant="success")
```

### Spring Boot (Reverse Proxy + REST + Identity Forwarding)

Route `/api/*` to Spring Boot (`:8080`) and `/` to RadUI (`:3000`, with `proxy_buffering off;` for SSE and streaming SSR), forwarding authenticated user identity headers to `user_id_resolver`:

```python
import httpx, radui as ui

SPRING_API = "http://127.0.0.1:8080/api"
app = ui.App("SpringAdmin", user_id_resolver=lambda req: req.headers.get("x-auth-subject"))

@app.command("orders.approve")
async def approve_order(ctx: ui.CommandContext):
    order_id = ctx.form_data["order_id"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{SPRING_API}/orders/{order_id}/approve")
        r.raise_for_status()
```

---

## 3. Frontend Frameworks (React & Next.js)

### Embedding Live RadUI Views (`/_gx/embed.js` + `<radui-view>`)

```tsx
"use client";
import { useEffect } from "react";

export function RadUIWidget({ view = "/analytics" }: { view?: string }) {
  useEffect(() => {
    const s = document.createElement("script");
    s.src = "https://ui.example.com/_gx/embed.js";
    s.async = true;
    document.body.appendChild(s);
    return () => { s.remove(); };
  }, []);
  return <radui-view src="https://ui.example.com" view={view} height="540px" />;
}
```

### Hosting Custom Elements Inside RadUI (M2.2)

```python
ui.custom_element(
    "acme-chart",
    props={"dataset": "q4-revenue"},
    event_commands={"point-selected": "chart.select"},
)
```

---

## 4. Databases & Storage

- **SQLite (Native):** `gx.App("App", state_backend=gx.SQLiteStateBackend("radui.db"))`
- **PostgreSQL (Native `psycopg` 3 + RLS):** `gx.App("App", state_backend=gx.PostgreSQLStateBackend("postgresql://user:pass@localhost/radui"))`
- **Redis (Native Distributed Cluster):** `gx.App("App", redis_url="redis://localhost:6379/0")`
- **MongoDB (Custom CRUD):** Run `pymongo` or async `motor` inside `ui.query()` and `@app.command`, calling `ui.invalidate_query(...)` on writes.
- **Apache CouchDB (Custom HTTP CRUD):** Call CouchDB REST endpoints via `httpx` inside `@app.command` and `ui.query()`, optionally bridging `_changes` into `app.notify()`.

---

## 5. Security & Production Troubleshooting

- **SSE / Streaming SSR Buffering:** Disable reverse-proxy buffering (`proxy_buffering off;` in Nginx, `X-Accel-Buffering: no`) for `/_gx/events` and `stream=True` routes.
- **CSRF & Origin Validation:** `/_gx/commands/{id}` enforces `_csrf` and same-origin `Origin`/`Sec-Fetch-Site` checks. Keep RadUI and backend APIs on the same origin behind your reverse proxy whenever possible.
- **Cross-Origin `<radui-view>`:** Configure `frame-ancestors` in CSP if embedding RadUI inside a different origin.
