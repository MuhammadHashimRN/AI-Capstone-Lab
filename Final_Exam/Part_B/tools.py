"""
Final Exam Part B — Tools (Self-RAG)
=====================================
Two @tool-decorated entry points the Self-RAG graph relies on:

  • query_knowledge_base — retrieve from the university ChromaDB index.
  • web_search          — DuckDuckGo fallback when the local KB has nothing
                          relevant to the user's query.

Both tools use Pydantic schemas with descriptive Field() docs so the LLM
can call them with valid arguments, and both return JSON-encoded strings
so they fit cleanly inside LangGraph ToolMessage payloads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.tools import tool
from pydantic import BaseModel, Field

HERE = Path(__file__).parent
CHROMA_DIR = HERE / "chroma_db"
COLLECTION_NAME = "university_kb"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ─── Lazy Chroma client ─────────────────────────────────────────────────────

_collection = None


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
        )
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_fn,
        )
    return _collection


# ─── Pydantic Schemas ───────────────────────────────────────────────────────

class KBQueryInput(BaseModel):
    """Input schema for the knowledge-base retrieval tool."""
    query: str = Field(
        description="Natural-language query about university courses, policies, faculty, or fees."
    )
    top_k: int = Field(
        default=5,
        description="Number of top results to return (default 5, max 20).",
        ge=1, le=20,
    )
    doc_type: Optional[str] = Field(
        default=None,
        description="Optional filter: 'catalog', 'policy', or 'faculty'.",
    )
    department: Optional[str] = Field(
        default=None,
        description="Optional filter by department code: 'CS', 'EE', 'BBA', or 'university'.",
    )


class WebSearchInput(BaseModel):
    """Input schema for the web-search fallback tool."""
    query: str = Field(description="Natural-language search query.")
    num_results: int = Field(
        default=3,
        description="Number of web results to return (default 3, max 10).",
        ge=1, le=10,
    )


# ─── Tool implementations ───────────────────────────────────────────────────

@tool(args_schema=KBQueryInput)
def query_knowledge_base(
    query: str,
    top_k: int = 5,
    doc_type: Optional[str] = None,
    department: Optional[str] = None,
) -> str:
    """Retrieve passages from the XYZ National University knowledge base.

    The knowledge base contains course descriptions, prerequisites, credit
    hours, academic policies (grading, GPA, attendance, fees, calendar),
    and a faculty directory. Use this tool whenever the user asks about
    *specific* university information. Skip it for greetings or general
    knowledge questions.
    """
    collection = get_collection()
    where: dict = {}
    if doc_type and department:
        where = {"$and": [{"doc_type": doc_type}, {"department": department}]}
    elif doc_type:
        where = {"doc_type": doc_type}
    elif department:
        where = {"department": department}

    kwargs: dict = {"query_texts": [query], "n_results": min(top_k, 20)}
    if where:
        kwargs["where"] = where

    res = collection.query(**kwargs)
    docs = res["documents"][0] if res["documents"] else []
    metas = res["metadatas"][0] if res["metadatas"] else []
    dists = res["distances"][0] if res.get("distances") else [None] * len(docs)

    items = [
        {"content": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(docs, metas, dists)
    ]
    return json.dumps({"query": query, "filter": where, "results": items}, default=str)


@tool(args_schema=WebSearchInput)
def web_search(query: str, num_results: int = 3) -> str:
    """Search the public web for an answer when the knowledge base has no
    relevant information. Returns title, snippet, and URL for each result.

    Use this ONLY after the knowledge-base retrieval has failed (all retrieved
    documents graded as irrelevant). Do not invoke it for routine questions
    answerable from the local catalog or policy PDFs.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return json.dumps({"error": "duckduckgo-search package not installed", "results": []})

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=min(num_results, 10)))
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": []})

    items = [
        {
            "title": r.get("title", ""),
            "snippet": r.get("body", r.get("snippet", "")),
            "url": r.get("href", r.get("url", "")),
        }
        for r in raw
    ]
    return json.dumps({"query": query, "results": items})


# ─── Tool registry ──────────────────────────────────────────────────────────

ALL_TOOLS = [query_knowledge_base, web_search]
