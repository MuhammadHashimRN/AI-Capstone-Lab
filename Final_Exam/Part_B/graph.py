"""
Final Exam Part B — Self-RAG LangGraph
=======================================
Pipeline (StateGraph):

       ┌──────────────┐
       │ route_query  │  decides whether retrieval is needed
       └──────┬───────┘
              │
   needs_ret? │
       ┌──────┴──────┐
       │             │
       ▼             ▼
  direct_answer   retrieve_node
       │             │
       │             ▼
       │       grade_documents       (per-doc relevance)
       │             │
       │      any relevant? ──no──► web_search_node ──► generate_node
       │             │ yes                              │
       │             ▼                                  ▼
       │       generate_node ◄────────────────── hallucination_check
       │             │                                  │
       │             ▼                              hallucinated?
       │      hallucination_check                       │
       │             │                       retry < max? loop back
       └─────────────┴──────────────────────────► END

State variables capture the full decision trail so callers (or
self_rag_agent.py) can render an execution trace.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tools import query_knowledge_base, web_search  # noqa: E402

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.1-8b-instant"
MAX_HALLUCINATION_RETRIES = 2


# ─── Helpers ────────────────────────────────────────────────────────────────

def get_llm(temperature: float = 0.0) -> ChatGroq:
    return ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=temperature)


def _llm_yesno(prompt: str) -> tuple[str, str]:
    """Send `prompt` to the LLM and parse a strict YES/NO + reason response.

    Returns (verdict, raw_text). verdict is "YES", "NO", or "UNKNOWN".
    """
    llm = get_llm(temperature=0.0)
    resp = llm.invoke([HumanMessage(content=prompt)])
    text = (resp.content or "").strip()
    upper = text.upper()
    if upper.startswith("YES"):
        return "YES", text
    if upper.startswith("NO"):
        return "NO", text
    # Fallback: look for the first standalone YES/NO token
    m = re.search(r"\b(YES|NO)\b", upper)
    return (m.group(1) if m else "UNKNOWN"), text


# ─── State ──────────────────────────────────────────────────────────────────

class SelfRAGState(TypedDict, total=False):
    query: str
    messages: Annotated[list[BaseMessage], add_messages]
    needs_retrieval: bool
    retrieval_reasoning: str
    retrieved_docs: list[dict]        # all docs returned by KB
    graded_docs: list[dict]           # subset graded relevant
    used_web_fallback: bool
    web_results: list[dict]
    generation: str
    hallucination_grounded: bool
    hallucination_reason: str
    retry_count: int
    decision_trace: list[str]
    final_answer: str


# ─── Node 1: route_query (adaptive retrieval decision) ─────────────────────

ROUTE_PROMPT = """You are a routing classifier for a University Course Advisory Agent.

Decide whether the user's query requires looking up the university's
internal documents (course catalogs, academic policies, faculty
directory) OR whether it can be answered from general knowledge or
conversational reply alone.

Use RETRIEVE when the query asks about:
- specific courses, course codes, credit hours, prerequisites, syllabi
- the university's grading scale, GPA rules, fees, registration policy,
  attendance rules, withdrawal policy, academic calendar
- faculty members, their departments, specializations, office locations,
  email addresses, designations
- programs, semester schedules, department-specific information

Use NO_RETRIEVE when the query is:
- a greeting or small talk ("Hi", "How are you?")
- a general-knowledge question that does not depend on this university's
  internal documents (e.g. "What does GPA stand for in general?",
  "What is Python?")
- a request to perform a generic task unrelated to the university

Respond with exactly two lines:
DECISION: RETRIEVE | NO_RETRIEVE
REASON: <one short sentence>

User query:
{query}
"""


def route_query_node(state: SelfRAGState) -> dict:
    query = state["query"]
    llm = get_llm(temperature=0.0)
    resp = llm.invoke([HumanMessage(content=ROUTE_PROMPT.format(query=query))])
    text = (resp.content or "").strip()
    decision = "RETRIEVE"
    reason = ""
    for line in text.splitlines():
        if line.upper().startswith("DECISION:"):
            decision = "NO_RETRIEVE" if "NO_RETRIEVE" in line.upper() else "RETRIEVE"
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    needs = decision == "RETRIEVE"
    trace = list(state.get("decision_trace", []))
    trace.append(f"route_query: {decision} — {reason or 'no reason given'}")
    return {
        "needs_retrieval": needs,
        "retrieval_reasoning": reason or text,
        "decision_trace": trace,
        "retry_count": 0,
    }


# ─── Node 2a: direct_answer (no retrieval) ──────────────────────────────────

DIRECT_PROMPT = """You are the University Course Advisory Agent.

The user's query has been classified as not requiring retrieval from the
university's documents. Reply in 1-3 sentences. If the user greets you,
respond cordially and invite them to ask about courses, policies, or
faculty. If the query is general knowledge that you can answer
confidently, do so concisely. Never invent university-specific facts.

User query: {query}
"""


def direct_answer_node(state: SelfRAGState) -> dict:
    llm = get_llm(temperature=0.2)
    resp = llm.invoke([HumanMessage(content=DIRECT_PROMPT.format(query=state["query"]))])
    answer = (resp.content or "").strip()
    trace = list(state.get("decision_trace", []))
    trace.append("direct_answer: produced reply without retrieval")
    return {
        "generation": answer,
        "final_answer": answer,
        "decision_trace": trace,
        "hallucination_grounded": True,
        "messages": [AIMessage(content=answer)],
    }


# ─── Node 2b: retrieve_node ─────────────────────────────────────────────────

def retrieve_node(state: SelfRAGState) -> dict:
    query = state["query"]
    raw = query_knowledge_base.invoke({"query": query, "top_k": 8})
    parsed = json.loads(raw)
    docs = parsed.get("results", [])
    trace = list(state.get("decision_trace", []))
    trace.append(f"retrieve_node: pulled {len(docs)} candidate chunks from ChromaDB")
    return {"retrieved_docs": docs, "decision_trace": trace}


# ─── Node 3: grade_documents ────────────────────────────────────────────────

GRADE_PROMPT = """You are a relevance grader for a retrieval system.

Decide whether the DOCUMENT contains information that helps answer the
USER QUESTION. A document is RELEVANT only if it directly addresses the
question; tangential or merely topical documents are NOT relevant.

USER QUESTION: {query}

DOCUMENT:
{document}

Reply with exactly two lines:
VERDICT: YES | NO
REASON: <one short sentence>
"""


def grade_documents_node(state: SelfRAGState) -> dict:
    query = state["query"]
    docs = state.get("retrieved_docs", [])
    relevant: list[dict] = []
    grades: list[str] = []
    for i, d in enumerate(docs):
        verdict, raw = _llm_yesno(
            GRADE_PROMPT.format(query=query, document=d["content"][:1500])
        )
        meta = d.get("metadata", {})
        grades.append(
            f"  doc[{i}] {meta.get('doc_type','?')}/{meta.get('section_title','?')[:50]} -> {verdict}"
        )
        if verdict == "YES":
            relevant.append({**d, "grade_verdict": verdict, "grade_reason": raw})

    trace = list(state.get("decision_trace", []))
    trace.append(
        f"grade_documents: kept {len(relevant)}/{len(docs)} as relevant\n" + "\n".join(grades)
    )
    return {"graded_docs": relevant, "decision_trace": trace}


# ─── Node 4: web_search_node (fallback) ────────────────────────────────────

def web_search_node(state: SelfRAGState) -> dict:
    query = state["query"]
    raw = web_search.invoke({"query": query, "num_results": 3})
    parsed = json.loads(raw)
    results = parsed.get("results", [])
    trace = list(state.get("decision_trace", []))
    if parsed.get("error"):
        trace.append(f"web_search: ERROR — {parsed['error']}")
    else:
        trace.append(f"web_search: pulled {len(results)} web results as fallback context")
    return {"web_results": results, "used_web_fallback": True, "decision_trace": trace}


# ─── Node 5: generate_node ──────────────────────────────────────────────────

GENERATE_PROMPT = """You are the University Course Advisory Agent for XYZ National University.

Answer the user's question using ONLY the supplied context. If the
context is not enough to answer, say so clearly. Cite the source for
key facts inline using the format [source: <section_title>].

USER QUESTION: {query}

CONTEXT:
{context}

Answer:"""


def _build_context(state: SelfRAGState) -> tuple[str, str]:
    """Assemble the context block and a source label."""
    if state.get("used_web_fallback") and state.get("web_results"):
        ctx_lines = []
        for i, r in enumerate(state["web_results"], 1):
            ctx_lines.append(
                f"[Web result {i}] {r.get('title','')} ({r.get('url','')})\n"
                f"{r.get('snippet','')}"
            )
        return "\n\n".join(ctx_lines), "web"
    if state.get("graded_docs"):
        ctx_lines = []
        for d in state["graded_docs"]:
            meta = d.get("metadata", {})
            ctx_lines.append(
                f"[source: {meta.get('section_title','?')} | {meta.get('source_file','?')}]\n"
                f"{d['content'][:1500]}"
            )
        return "\n\n".join(ctx_lines), "kb"
    return "(no context available)", "none"


def generate_node(state: SelfRAGState) -> dict:
    context, src = _build_context(state)
    llm = get_llm(temperature=0.1)
    resp = llm.invoke([HumanMessage(content=GENERATE_PROMPT.format(
        query=state["query"], context=context,
    ))])
    answer = (resp.content or "").strip()
    trace = list(state.get("decision_trace", []))
    retry = state.get("retry_count", 0)
    label = "retry " + str(retry) if retry else "initial"
    trace.append(f"generate_node: produced {label} answer using {src} context")
    return {
        "generation": answer,
        "decision_trace": trace,
        "messages": [AIMessage(content=answer)],
    }


# ─── Node 6: hallucination_check ───────────────────────────────────────────

HALLUCINATION_PROMPT = """You are a hallucination detector.

CONTEXT (the only information the assistant should rely on):
{context}

ASSISTANT ANSWER:
{answer}

Is every factual claim in the assistant's answer supported by the
context? A claim is supported if the context contains the same number,
name, or rule. Vague disclaimers ("I don't have information on …")
are always grounded.

Reply with exactly two lines:
VERDICT: YES | NO
REASON: <one short sentence>
"""


def hallucination_check_node(state: SelfRAGState) -> dict:
    context, _ = _build_context(state)
    verdict, raw = _llm_yesno(
        HALLUCINATION_PROMPT.format(context=context, answer=state.get("generation", ""))
    )
    grounded = verdict == "YES"
    trace = list(state.get("decision_trace", []))
    trace.append(f"hallucination_check: grounded={grounded}  ({verdict})")
    retry = state.get("retry_count", 0)
    if not grounded:
        retry += 1
    return {
        "hallucination_grounded": grounded,
        "hallucination_reason": raw,
        "retry_count": retry,
        "decision_trace": trace,
    }


# ─── Node 7: finalize ───────────────────────────────────────────────────────

DISCLAIMER = (
    "\n\n[Note: I could not fully verify this answer against the university's "
    "documents after multiple attempts. Please confirm with the official sources.]"
)


def finalize_node(state: SelfRAGState) -> dict:
    generation = state.get("generation", "")
    final = generation
    trace = list(state.get("decision_trace", []))
    if not state.get("hallucination_grounded", True):
        final = generation + DISCLAIMER
        trace.append("finalize: appended unverified disclaimer (retry limit reached)")
    else:
        trace.append("finalize: response grounded — returning to user")
    return {
        "final_answer": final,
        "decision_trace": trace,
    }


# ─── Routers ────────────────────────────────────────────────────────────────

def route_after_route_query(state: SelfRAGState) -> str:
    return "retrieve" if state.get("needs_retrieval") else "direct"


def route_after_grading(state: SelfRAGState) -> str:
    return "generate" if state.get("graded_docs") else "web_search"


def route_after_hallucination(state: SelfRAGState) -> str:
    if state.get("hallucination_grounded"):
        return "finalize"
    if state.get("retry_count", 0) >= MAX_HALLUCINATION_RETRIES:
        return "finalize"
    return "regenerate"


# ─── Graph build ────────────────────────────────────────────────────────────

def build_self_rag_graph():
    g = StateGraph(SelfRAGState)
    g.add_node("route_query", route_query_node)
    g.add_node("direct_answer", direct_answer_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("grade", grade_documents_node)
    g.add_node("web_search", web_search_node)
    g.add_node("generate", generate_node)
    g.add_node("hallucination_check", hallucination_check_node)
    g.add_node("finalize", finalize_node)

    g.set_entry_point("route_query")

    g.add_conditional_edges(
        "route_query",
        route_after_route_query,
        {"direct": "direct_answer", "retrieve": "retrieve"},
    )

    g.add_edge("direct_answer", END)

    g.add_edge("retrieve", "grade")

    g.add_conditional_edges(
        "grade",
        route_after_grading,
        {"generate": "generate", "web_search": "web_search"},
    )

    g.add_edge("web_search", "generate")
    g.add_edge("generate", "hallucination_check")

    g.add_conditional_edges(
        "hallucination_check",
        route_after_hallucination,
        {"finalize": "finalize", "regenerate": "generate"},
    )

    g.add_edge("finalize", END)

    return g.compile()


if __name__ == "__main__":
    if not GROQ_API_KEY:
        print("[ERROR] GROQ_API_KEY not set.")
        sys.exit(1)

    graph = build_self_rag_graph()
    test_q = "What are the prerequisites for CS-301 Artificial Intelligence?"
    result = graph.invoke({"query": test_q, "messages": [HumanMessage(content=test_q)]})
    print("=" * 60)
    print("QUERY :", test_q)
    print("=" * 60)
    print("\n".join(result["decision_trace"]))
    print("\nFINAL :", result["final_answer"])
