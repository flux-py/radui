"""Comprehensive Integration Guide for Backend, Frontend, and Database stacks."""

from __future__ import annotations

import radui as ui
from docs_site.core import app


@app.page("/integrations")
def integrations_page():
    return ui.column(
        ui.badge("Ecosystem & Stack Integration", variant="primary"),
        ui.heading("RadUI Integration Guide", level=1),
        ui.text(
            "Practical, verified patterns for integrating RadUI into existing Python and JVM backends, "
            "React/Next.js frontends, and relational, document, or in-memory databases.",
            variant="lead",
        ),
        ui.card(
            ui.heading("Integration Classification Matrix", level=3),
            ui.data_grid(
                headers=["Target", "Integration Type", "What RadUI Handles", "What You Configure"],
                rows=[
                    ["FastAPI / Starlette", "Native ASGI", "Full SSR, SSE, SPA nav, commands, CSRF", "Mount radui_app.asgi() under /ui or share lifespan"],
                    ["Flask", "Adapter (WSGI->ASGI)", "UI rendering, commands, SSE, sessions", "Mount Flask via WSGIMiddleware or reverse-proxy side-by-side"],
                    ["Django", "Adapter (ASGI / ORM)", "UI rendering, async commands, CSRF", "Compose ASGI router + wrap Django ORM calls in sync/thread handlers"],
                    ["Spring Boot", "Custom HTTP / Proxy", "UI shell, SSE patches, CSRF, SPA nav", "Nginx/Envoy route split + user_id_resolver + httpx calls to Spring API"],
                    ["React / Next.js", "Embed / Micro-Frontend", "<radui-view> iframe embed or Web Components", "Include /_gx/embed.js or route split (/ui -> RadUI, /app -> Next.js)"],
                    ["SQLite", "Native Built-in", "SQLiteStateBackend, SQLiteJobBackend, Idempotency", "Pass backend=SQLiteStateBackend('radui.db')"],
                    ["PostgreSQL", "Native Built-in", "PostgreSQLStateBackend (psycopg 3 + RLS)", "Pass DSN to PostgreSQLStateBackend(dsn)"],
                    ["Redis", "Native Built-in", "State, Events, Jobs, SSE Governance, Idempotency", "Pass redis_url or Redis*Backend instances"],
                    ["MongoDB", "Custom App Layer", "Command validation, query SWR cache, SSE patches", "Run pymongo/motor inside @app.command and ui.query()"],
                    ["Apache CouchDB", "Custom HTTP / Changes", "Command validation, toast/event broadcast", "Call CouchDB REST via httpx; bridge _changes to app.notify()"],
                ],
                searchable=True,
                sortable=True,
                page_size=12,
            ),
            title="Native vs Adapter vs Custom Integrations",
        ),
        ui.heading("1. Backend Framework Integrations", level=2, id="backends"),
        ui.accordion(
            ui.accordion_item(
                "FastAPI (Native ASGI Mount)",
                ui.column(
                    ui.text("Mount a RadUI app inside FastAPI using Starlette/FastAPI app.mount(), or mount FastAPI API routes alongside RadUI:"),
                    ui.code_block(
                        "from fastapi import FastAPI\n"
                        "import radui as ui\n\n"
                        "api = FastAPI()\n"
                        "radui_app = ui.App('EmbeddedUI')\n\n"
                        "@radui_app.page('/')\n"
                        "def ui_home():\n"
                        "    return ui.heading('Served from RadUI inside FastAPI')\n\n"
                        "@api.get('/api/health')\n"
                        "def api_health():\n"
                        "    return {'ok': True}\n\n"
                        "api.mount('/ui', radui_app.asgi())",
                        language="python",
                    ),
                    gap=8,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Flask (WSGI Adapter / Side-by-Side ASGI)",
                ui.column(
                    ui.text("Wrap a Flask WSGI app with Starlette/asgiref or route /api/* to Flask and /ui/* to RadUI behind uvicorn/Nginx:"),
                    ui.code_block(
                        "from flask import Flask, jsonify\n"
                        "from a2wsgi import WSGIMiddleware  # or asgiref.wsgi.WsgiToAsgi\n"
                        "from starlette.routing import Mount\n"
                        "import radui as ui\n\n"
                        "flask_app = Flask(__name__)\n"
                        "@flask_app.get('/api/orders')\n"
                        "def list_orders():\n"
                        "    return jsonify([{'id': 1, 'status': 'paid'}])\n\n"
                        "radui_app = ui.App('FlaskBridge', custom_middleware=[])\n"
                        "# Run Flask on :5000 and RadUI on :3000, or mount WSGIMiddleware(flask_app) in Starlette:\n"
                        "# Starlette(routes=[Mount('/api', app=WSGIMiddleware(flask_app)), Mount('/', app=radui_app.asgi())])",
                        language="python",
                    ),
                    gap=8,
                ),
                open=False,
            ),
            ui.accordion_item(
                "Django (ASGI Composition + ORM Bridge)",
                ui.column(
                    ui.text("Run Django's ASGI application and RadUI together under Uvicorn, sharing session/user identity via user_id_resolver:"),
                    ui.code_block(
                        "import radui as ui\n"
                        "# from myapp.models import Invoice\n\n"
                        "def resolve_django_user(request):\n"
                        "    # Verify signed cookie or proxy header forwarded from Django auth\n"
                        "    return request.headers.get('x-authenticated-user')\n\n"
                        "radui_app = ui.App('DjangoUI', user_id_resolver=resolve_django_user)\n\n"
                        "@radui_app.command('invoice.mark_paid')\n"
                        "def mark_paid(ctx: ui.CommandContext):\n"
                        "    # Synchronous @app.command handlers run safely in anyio worker threads\n"
                        "    inv_id = ctx.form_data.get('invoice_id')\n"
                        "    # Invoice.objects.filter(id=inv_id).update(status='paid')\n"
                        "    radui_app.notify(f'Invoice {inv_id} marked paid', variant='success')",
                        language="python",
                    ),
                    gap=8,
                ),
                open=False,
            ),
            ui.accordion_item(
                "Spring Boot (Reverse-Proxy + REST + Identity Forwarding)",
                ui.column(
                    ui.text("Keep Spring Boot authoritative for domain/JPA logic on :8080 and run RadUI on :3000 behind Nginx/Envoy:"),
                    ui.code_block(
                        "# 1. RadUI calls Spring Boot REST endpoints via httpx inside @app.command / ui.query\n"
                        "import httpx, radui as ui\n\n"
                        "SPRING_API = 'http://127.0.0.1:8080/api'\n"
                        "app = ui.App('SpringAdmin', user_id_resolver=lambda req: req.headers.get('x-auth-subject'))\n\n"
                        "@app.command('orders.approve')\n"
                        "async def approve_order(ctx: ui.CommandContext):\n"
                        "    order_id = ctx.form_data['order_id']\n"
                        "    async with httpx.AsyncClient(timeout=5.0) as client:\n"
                        "        r = await client.post(f'{SPRING_API}/orders/{order_id}/approve')\n"
                        "        r.raise_for_status()\n\n"
                        "# 2. Nginx location blocks:\n"
                        "# location /api/ { proxy_pass http://127.0.0.1:8080; }\n"
                        "# location /    { proxy_pass http://127.0.0.1:3000; proxy_buffering off; }",
                        language="python",
                    ),
                    gap=8,
                ),
                open=False,
            ),
        ),
        ui.heading("2. Frontend Framework Integrations", level=2, id="frontends"),
        ui.accordion(
            ui.accordion_item(
                "React & Next.js (<radui-view> Embed + Micro-Frontend Routing)",
                ui.column(
                    ui.text("Embed any live RadUI route inside React or Next.js using /_gx/embed.js (<radui-view>), or split routes at the reverse proxy:"),
                    ui.code_block(
                        "// React / Next.js Client Component\n"
                        "'use client';\n"
                        "import { useEffect } from 'react';\n\n"
                        "export function RadUIWidget({ view = '/analytics' }: { view?: string }) {\n"
                        "  useEffect(() => {\n"
                        "    const s = document.createElement('script');\n"
                        "    s.src = 'https://ui.example.com/_gx/embed.js';\n"
                        "    s.async = true;\n"
                        "    document.body.appendChild(s);\n"
                        "    return () => { s.remove(); };\n"
                        "  }, []);\n"
                        "  return <radui-view src='https://ui.example.com' view={view} height='540px' />;\n"
                        "}",
                        language="tsx",
                    ),
                    gap=8,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Embedding External Web Components Inside RadUI (M2.2)",
                ui.column(
                    ui.text("Host React/Lit/Stencil Custom Elements directly inside RadUI pages with ui.custom_element(...) and bridge events back to Python:"),
                    ui.code_block(
                        "ui.custom_element(\n"
                        "    'acme-chart',\n"
                        "    props={'dataset': 'q4-revenue'},\n"
                        "    event_commands={'point-selected': 'chart.select'},\n"
                        ")",
                        language="python",
                    ),
                    gap=8,
                ),
                open=False,
            ),
        ),
        ui.heading("3. Databases & Storage Integrations", level=2, id="databases"),
        ui.accordion(
            ui.accordion_item(
                "SQLite, PostgreSQL & Redis (Native Built-in Backends)",
                ui.column(
                    ui.text("RadUI ships first-class backends for SQLite (WAL mode), PostgreSQL (psycopg 3), and Redis (cluster-ready state, events, jobs, SSE governance):"),
                    ui.code_block(
                        "import radui as gx\n\n"
                        "# SQLite (single-host persistent WAL)\n"
                        "sqlite_app = gx.App('SQLiteApp', state_backend=gx.SQLiteStateBackend('radui.db'))\n\n"
                        "# PostgreSQL (psycopg 3 + tenant RLS)\n"
                        "pg_app = gx.App('PGApp', state_backend=gx.PostgreSQLStateBackend('postgresql://user:pass@localhost/radui'))\n\n"
                        "# Redis (multi-worker distributed state + events + jobs)\n"
                        "redis_app = gx.App('RedisApp', redis_url='redis://localhost:6379/0')",
                        language="python",
                    ),
                    gap=8,
                ),
                open=True,
            ),
            ui.accordion_item(
                "MongoDB (Custom CRUD via PyMongo / Motor + SWR Query Cache)",
                ui.column(
                    ui.text("Use ui.query() for cached reads and @app.command for writes, calling ui.invalidate_query() to refresh UI:"),
                    ui.code_block(
                        "from pymongo import MongoClient\n"
                        "import radui as ui\n\n"
                        "mongo = MongoClient('mongodb://localhost:27017')\n"
                        "orders_col = mongo['shop']['orders']\n\n"
                        "def fetch_orders():\n"
                        "    return list(orders_col.find({}, {'_id': 0}).limit(25))\n\n"
                        "@app.command('mongo.order.create')\n"
                        "def create_order(ctx: ui.CommandContext):\n"
                        "    orders_col.insert_one({'item': ctx.form_data['item'], 'qty': int(ctx.form_data['qty'])})\n"
                        "    ui.invalidate_query('orders.list')",
                        language="python",
                    ),
                    gap=8,
                ),
                open=False,
            ),
            ui.accordion_item(
                "Apache CouchDB (HTTP Document CRUD + _changes Bridge)",
                ui.column(
                    ui.text("Interact with CouchDB's HTTP API using httpx inside @app.command and stream _changes notifications into RadUI:"),
                    ui.code_block(
                        "import httpx, radui as ui\n\n"
                        "COUCH = 'http://admin:password@127.0.0.1:5984/tasks'\n\n"
                        "@app.command('couch.task.add')\n"
                        "async def add_task(ctx: ui.CommandContext):\n"
                        "    doc = {'title': ctx.form_data['title'], 'done': False}\n"
                        "    async with httpx.AsyncClient(timeout=5.0) as client:\n"
                        "        r = await client.post(COUCH, json=doc)\n"
                        "        r.raise_for_status()\n"
                        "    ui.invalidate_query('couch.tasks')",
                        language="python",
                    ),
                    gap=8,
                ),
                open=False,
            ),
        ),
        ui.heading("4. Production, Auth & Troubleshooting Checklist", level=2, id="production"),
        ui.card(
            ui.data_grid(
                headers=["Topic", "Guidance"],
                rows=[
                    ["Reverse Proxy Buffering", "Set proxy_buffering off and X-Accel-Buffering: no for /_gx/events (SSE) and stream=True routes."],
                    ["Session & Auth Bridging", "Pass user_id_resolver=fn(request) to integrate SSO, JWT, Django, or Spring Security headers."],
                    ["Cross-Origin Embeds", "Set frame-ancestors in CSP and configure CORS / Origin policies when embedding <radui-view> cross-origin."],
                    ["Sync vs Async DB Drivers", "Sync @app.command handlers run in worker threads; use async def commands for motor/httpx/psycopg async."],
                ],
                searchable=False,
                sortable=False,
                page_size=10,
            ),
            title="Production & Security Checklist",
        ),
        gap=16,
    )
