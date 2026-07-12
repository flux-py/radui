"""RADUI Showcase Application A: AI Agent & RAG Workbench.

Demonstrates:
- Streaming LLM conversation with ChatView, ChatMessage, and ChatInput
- Background RAG embedding & document ingestion job with JobPanel and progress
- Agent tool execution journal with StepTimeline
- Human-in-the-loop action approval with ActionCard
- Live runtime inspector telemetry (debug=True)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import radui as gx

# State definitions
active_agent = gx.state("agent_name", "RADUI Research Agent", scope="session")
rag_status = gx.state("rag_status", "Ready to ingest documents", scope="session")
chat_prompt = gx.state("message", "", scope="session")
chat_history = gx.state(
    "chat_history",
    [
        {"role": "assistant", "content": "Hello! I am your RADUI AI Agent. You can submit questions, run RAG ingestion jobs, or inspect tool execution steps below.", "timestamp": "Just now"},
    ],
    scope="session",
)
approval_status = gx.state("approval_status", "pending", scope="session")
tool_steps = gx.state(
    "tool_steps",
    [
        {"title": "Initialize Session", "status": "completed", "details": "Loaded system prompt & MCP tools", "timestamp": "10:00:01"},
        {"title": "Connect Vector Store", "status": "completed", "details": "Connected to local in-memory index", "timestamp": "10:00:02"},
        {"title": "Awaiting User Query", "status": "in_progress", "details": "Agent listening on SSE channel", "timestamp": "10:00:03"},
    ],
    scope="session",
)

app = gx.App("AI Agent & RAG Workbench", app_id="ai-agent-workbench", debug=True)


@app.job("rag.index_documents")
async def index_documents(ctx: gx.JobContext, num_docs: int = 5) -> dict:
    """Simulates background chunking, embedding generation, and vector indexing."""
    await ctx.progress(10, "Scanning documents directory...")
    await asyncio.sleep(0.3)

    for i in range(1, num_docs + 1):
        if ctx.is_cancelled:
            return {"cancelled": True, "indexed": i - 1}
        pct = 10 + int((i / num_docs) * 80)
        await ctx.progress(pct, f"Embedding chunk {i}/{num_docs} with text-embedding-3...")
        await asyncio.sleep(0.25)

    await ctx.progress(100, "Vector index updated successfully!")
    rag_status.value = f"Indexed {num_docs} documents successfully at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
    return {"indexed": num_docs, "status": "completed"}


@app.command("chat.send")
async def send_message(ctx: gx.CommandContext) -> None:
    message = ctx.form_data.get("message", chat_prompt.value).strip()
    if not message:
        return
    chat_prompt.value = ""

    history = list(chat_history.value)
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    history.append({"role": "user", "content": message, "timestamp": now_str})

    # Synthetic agent response
    response = (
        f"I received your inquiry: '{message}'. RAG status: {rag_status.value}. "
        "I have cross-referenced the active vector index and confirmed alignment with the RADUI Core architecture."
    )
    history.append({"role": "assistant", "content": response, "timestamp": now_str})
    chat_history.value = history

    # Update timeline
    steps = list(tool_steps.value)
    steps.append({"title": f"Processed Query: {message[:25]}...", "status": "completed", "details": f"Generated {len(response)} chars", "timestamp": now_str})
    tool_steps.value = steps


@app.command("rag.start_index")
async def start_indexing(ctx: gx.CommandContext) -> None:
    await index_documents.submit(ctx, idempotency_key=ctx.action_id, num_docs=8)


@app.command("action.approve")
def approve_action(ctx: gx.CommandContext) -> None:
    approval_status.value = "approved"


@app.command("action.reject")
def reject_action(ctx: gx.CommandContext) -> None:
    approval_status.value = "rejected"


@app.page("/")
def home():
    messages = [
        gx.chat_message(m["content"], role=m["role"], timestamp=m["timestamp"])
        for m in chat_history.value
    ]

    action_state = approval_status.value
    if action_state == "approved":
        action_widget = gx.callout("Tool execution approved! Safe command dispatched to cluster.", variant="success")
    elif action_state == "rejected":
        action_widget = gx.callout("Tool execution rejected by human supervisor.", variant="danger")
    else:
        action_widget = gx.action_card(
            title="External Tool Call: Deploy Staging Worker",
            description="Agent is requesting permission to spin up worker replica 'worker-ag-9' with 4GB RAM.",
            approve_command="action.approve",
            reject_command="action.reject",
            confirm_label="Approve Execution",
            cancel_label="Deny",
            metadata={"Cluster": "us-east-prod", "Target": "worker-ag-9", "Cost": "$0.04/hr"},
            id="agent-action-card",
        )

    return gx.column(
        gx.row(
            gx.heading("AI Agent & RAG Workbench", level=1),
            gx.badge("MIL-0.5", variant="primary"),
            gx.badge("Debug Telemetry Active", variant="success"),
            justify="space-between",
            align="center",
        ),
        gx.text("Full-stack autonomous agent cockpit with real-time SSE streaming, tool auditing, and background RAG indexing.", variant="muted"),
        gx.divider(),
        gx.grid(
            gx.column(
                gx.card(
                    gx.heading("Agent Conversation Stream", level=3),
                    gx.chat_view(messages, id="workbench-chat"),
                    gx.spacer(8),
                    gx.form(
                        "chat.send",
                        gx.row(
                            gx.input("message", bind=chat_prompt, placeholder="Ask the agent anything..."),
                            gx.button("Send Query", variant="primary"),
                            gap=8,
                        ),
                        id="chat-form",
                    ),
                ),
                gx.spacer(16),
                gx.card(
                    gx.heading("Human-In-The-Loop Governance", level=3),
                    action_widget,
                ),
            ),
            gx.column(
                gx.card(
                    gx.heading("Vector Store & RAG Ingestion", level=3),
                    gx.callout(bind=rag_status, variant="info", id="rag-callout"),
                    gx.spacer(10),
                    gx.form(
                        "rag.start_index",
                        gx.button("Trigger Ingestion Job (8 docs)", variant="primary"),
                        id="rag-form",
                    ),
                    gx.spacer(12),
                    gx.job_panel(index_documents, id="rag-job-panel"),
                ),
                gx.spacer(16),
                gx.card(
                    gx.heading("Agent Execution Journal", level=3),
                    gx.step_timeline(tool_steps.value, id="agent-timeline"),
                ),
            ),
            columns=2,
            gap=20,
        ),
    )


if __name__ == "__main__":
    app.run(port=8001)

