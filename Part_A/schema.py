"""
Lab 8: API Layer — Request/Response Schemas
===========================================
Pydantic models for the FastAPI /chat and /stream endpoints.
Thread ID bridges stateless HTTP to the stateful LangGraph checkpointer.
"""

import uuid
from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for /chat and /stream endpoints."""

    message: str = Field(
        ...,
        description="User message to the inventory agent",
        min_length=1,
        max_length=2000,
        examples=["Check inventory for SKU-001 and recommend a reorder if needed."],
    )
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description=(
            "Conversation thread identifier. Reuse the same thread_id to "
            "continue a prior session; omit to start a new one."
        ),
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )


class ChatResponse(BaseModel):
    """Response payload for the synchronous /chat endpoint."""

    thread_id: str = Field(..., description="Thread ID for this conversation")
    answer: str = Field(..., description="Agent's final answer")
    tools_called: list[str] = Field(
        default_factory=list,
        description="Names of tools invoked during the reasoning loop",
    )
    latency_ms: int = Field(..., description="End-to-end processing time in milliseconds")
    guardrail_passed: bool = Field(
        default=True,
        description="False when the input was blocked by security guardrails",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the request could not be completed",
    )


class HealthResponse(BaseModel):
    """Response payload for the /health endpoint."""

    status: str = Field(..., description="'ok' when the service is healthy")
    model: str = Field(..., description="LLM model name in use")
    vector_db: str = Field(..., description="ChromaDB availability: 'ok' or 'missing'")
    checkpoint_db: str = Field(..., description="SQLite checkpoint DB availability: 'ok' or 'missing'")
    groq_api_configured: bool = Field(..., description="True when GROQ_API_KEY is set")
