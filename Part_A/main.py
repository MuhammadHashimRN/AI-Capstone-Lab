"""
Lab 8: The API Layer (FastAPI)
==============================
Exposes the LangGraph inventory agent as a RESTful HTTP API.

Endpoints:
  POST /chat   — Synchronous stateful chat (thread_id → SQLite checkpointer)
  POST /stream — Server-Sent Events (SSE) streaming of agent reasoning steps
  GET  /health — Service health and configuration status

Key design: thread_id bridges stateless HTTP to the stateful LangGraph graph.
Every request with the same thread_id resumes the previous conversation from
the SQLite checkpoint store — no session affinity required at the load balancer.
"""

import json
import os
import sqlite3
import sys
import time
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    CHECKPOINT_DB_PATH,
    CHROMA_PERSIST_DIR,
    GROQ_API_KEY,
    GROQ_MODEL,
    enable_langsmith,
)
from schema import ChatRequest, ChatResponse, HealthResponse

# Activate LangSmith tracing when the env var is set
enable_langsmith()


# ─── FastAPI Application ───────────────────────────────────────────────────

app = FastAPI(
    title="Dynamic Inventory Reorder Agent API",
    description=(
        "RESTful API for the AI-powered inventory management agent built with "
        "LangGraph + Groq. Supports stateful multi-turn conversations via thread_id."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Graph Factory ─────────────────────────────────────────────────────────

def _build_persistent_graph():
    """Build the secured ReAct graph wired to the SQLite checkpointer.

    Returns (graph, conn) so the caller can close the connection when done.
    The secured graph adds the guardrail_node and output-sanitisation layer
    on top of the standard ReAct loop (Lab 6 feature).
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    from secured_graph import build_secured_graph

    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # build_secured_graph returns (compiled, conn) when with_persistence=True,
    # but we handle the connection ourselves for proper lifecycle management.
    graph = build_secured_graph()

    # Recompile with our checkpointer so thread_id state is persisted.
    from secured_graph import (
        SecuredAgentState,
        guardrail_node,
        agent_node,
        alert_node,
        tool_node,
        route_after_guardrail,
        route_after_agent,
    )
    from langgraph.graph import END, StateGraph

    workflow = StateGraph(SecuredAgentState)
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("alert", alert_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("guardrail")
    workflow.add_conditional_edges(
        "guardrail", route_after_guardrail, {"agent": "agent", "alert": "alert"}
    )
    workflow.add_conditional_edges(
        "agent", route_after_agent, {"tools": "tools", END: END}
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("alert", END)

    compiled = workflow.compile(checkpointer=checkpointer)
    return compiled, conn


def _build_streaming_graph():
    """Build a lightweight ReAct graph (no checkpointer) for the SSE stream endpoint."""
    from graph import build_react_graph
    return build_react_graph()


# ─── Health Check ──────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Infrastructure"])
def health_check():
    """Returns service health status and configuration readiness."""
    return HealthResponse(
        status="ok",
        model=GROQ_MODEL,
        vector_db="ok" if os.path.exists(CHROMA_PERSIST_DIR) else "missing",
        checkpoint_db="ok" if os.path.exists(CHECKPOINT_DB_PATH) else "missing",
        groq_api_configured=bool(GROQ_API_KEY),
    )


# ─── Synchronous Chat ──────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
def chat(request: ChatRequest):
    """Stateful chat endpoint.

    Bridges stateless HTTP to the stateful LangGraph agent via `thread_id`.
    Pass the same `thread_id` across requests to continue a conversation.
    Omit it (or pass a new UUID) to start fresh.

    The request passes through the security guardrail before reaching the
    reasoning loop. Blocked inputs receive a refusal rather than an error.
    """
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured. Set it as an environment variable.",
        )

    start_time = time.time()
    graph, conn = None, None

    try:
        graph, conn = _build_persistent_graph()
        config = {"configurable": {"thread_id": request.thread_id}}

        result = graph.invoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )

        latency_ms = round((time.time() - start_time) * 1000)

        # Parse the result state
        answer = ""
        tools_called: list[str] = []
        guardrail_passed = True

        # Check guardrail verdict stored in state
        if result.get("guardrail_verdict") == "UNSAFE":
            guardrail_passed = False

        for msg in result.get("messages", []):
            if isinstance(msg, AIMessage):
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tools_called.append(tc["name"])
                elif msg.content:
                    answer = msg.content  # Last non-tool-call AI message is the answer

        return ChatResponse(
            thread_id=request.thread_id,
            answer=answer,
            tools_called=tools_called,
            latency_ms=latency_ms,
            guardrail_passed=guardrail_passed,
        )

    except Exception as exc:
        latency_ms = round((time.time() - start_time) * 1000)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    finally:
        if conn:
            conn.close()


# ─── Streaming Chat (SSE) ──────────────────────────────────────────────────

async def _sse_generator(message: str, thread_id: str) -> AsyncGenerator[str, None]:
    """Yield Server-Sent Event strings for each step in the agent reasoning loop.

    Event types emitted:
      tool_call   — agent decided to call a tool
      tool_result — tool returned a result
      message     — agent produced a text chunk
      done        — stream completed successfully
      error       — an exception occurred
    """
    try:
        graph = _build_streaming_graph()
        config = {"configurable": {"thread_id": thread_id}}

        for chunk in graph.stream(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_output in chunk.items():
                messages = node_output.get("messages", [])
                for msg in messages:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tc in msg.tool_calls:
                            event = {
                                "event": "tool_call",
                                "node": node_name,
                                "tool": tc["name"],
                                "args": tc["args"],
                            }
                            yield f"data: {json.dumps(event)}\n\n"
                        if msg.content:
                            yield f"data: {json.dumps({'event': 'thought', 'node': node_name, 'content': msg.content[:300]})}\n\n"

                    elif isinstance(msg, AIMessage) and msg.content:
                        yield f"data: {json.dumps({'event': 'message', 'node': node_name, 'content': msg.content})}\n\n"

                    elif hasattr(msg, "name") and msg.name:
                        yield f"data: {json.dumps({'event': 'tool_result', 'tool': msg.name, 'content': str(msg.content)[:500]})}\n\n"

        yield f"data: {json.dumps({'event': 'done', 'thread_id': thread_id})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'event': 'error', 'detail': str(exc)})}\n\n"


@app.post("/stream", tags=["Agent"])
async def stream_chat(request: ChatRequest):
    """Streaming chat endpoint using Server-Sent Events (SSE).

    Returns a stream of agent steps (tool calls, tool results, messages) as
    newline-delimited JSON events. Clients should read the stream until they
    receive an event with `"event": "done"`.

    Example curl:
        curl -N -X POST http://localhost:8000/stream \\
             -H "Content-Type: application/json" \\
             -d '{"message": "Check SKU-001 inventory", "thread_id": "test-01"}'
    """
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured.",
        )

    return StreamingResponse(
        _sse_generator(request.message, request.thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Dev Server ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("Starting Dynamic Inventory Reorder Agent API...")
    print(f"  Model       : {GROQ_MODEL}")
    print(f"  API key set : {bool(GROQ_API_KEY)}")
    print(f"  Docs        : http://localhost:8000/docs")
    print()

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
