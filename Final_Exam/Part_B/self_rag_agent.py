"""
Final Exam Part B — Self-RAG Agent (Interactive CLI)
=====================================================
Entry point for running the University Course Advisory Agent.

Modes
-----
  • Default (no args)           : single demo query + execution trace.
  • --interactive               : REPL-style chat loop.
  • --query "your question"     : answer a single query and exit.
  • --trace                     : print the full decision trace.
  • --json                      : dump the final state as JSON
                                  (useful for the evaluation harness).

Examples
--------
    python self_rag_agent.py --interactive
    python self_rag_agent.py --query "What does GPA stand for?"
    python self_rag_agent.py --query "Who teaches CS-301?" --trace --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from langchain_core.messages import HumanMessage

from graph import build_self_rag_graph  # noqa: E402


def run_query(graph, query: str) -> dict[str, Any]:
    t0 = time.time()
    result = graph.invoke({
        "query": query,
        "messages": [HumanMessage(content=query)],
        "decision_trace": [],
        "retry_count": 0,
    })
    result["latency_ms"] = round((time.time() - t0) * 1000)
    return result


def render_terminal(query: str, result: dict[str, Any], show_trace: bool) -> None:
    line = "=" * 72
    print(line)
    print(f"QUERY:  {query}")
    print(line)
    if show_trace:
        print("\nDECISION TRACE")
        print("-" * 72)
        for step in result.get("decision_trace", []):
            print(step)
        print("-" * 72)
        print(f"needs_retrieval        : {result.get('needs_retrieval')}")
        print(f"used_web_fallback      : {result.get('used_web_fallback', False)}")
        print(f"retry_count            : {result.get('retry_count', 0)}")
        print(f"hallucination_grounded : {result.get('hallucination_grounded')}")
        print(f"latency_ms             : {result.get('latency_ms')}")
    print("\nFINAL ANSWER")
    print("-" * 72)
    print(result.get("final_answer") or result.get("generation") or "(no answer)")
    print(line)


def to_json(query: str, result: dict[str, Any]) -> dict[str, Any]:
    """Trim the state down to JSON-safe primitives."""
    return {
        "query": query,
        "final_answer": result.get("final_answer") or result.get("generation", ""),
        "needs_retrieval": result.get("needs_retrieval"),
        "retrieval_reasoning": result.get("retrieval_reasoning", ""),
        "used_web_fallback": result.get("used_web_fallback", False),
        "retrieved_doc_count": len(result.get("retrieved_docs") or []),
        "graded_doc_count": len(result.get("graded_docs") or []),
        "web_result_count": len(result.get("web_results") or []),
        "retry_count": result.get("retry_count", 0),
        "hallucination_grounded": result.get("hallucination_grounded"),
        "decision_trace": result.get("decision_trace", []),
        "latency_ms": result.get("latency_ms"),
        "graded_doc_metadata": [
            d.get("metadata", {}) for d in result.get("graded_docs") or []
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-RAG University Course Advisory Agent")
    parser.add_argument("--query", "-q", type=str, default=None,
                        help="Run a single query and exit.")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Start an interactive REPL.")
    parser.add_argument("--trace", "-t", action="store_true",
                        help="Print the full decision trace.")
    parser.add_argument("--json", action="store_true",
                        help="Print the final state as JSON.")
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        print("[ERROR] GROQ_API_KEY is not set. Export it before running.", file=sys.stderr)
        return 1

    graph = build_self_rag_graph()

    if args.interactive:
        print("Self-RAG Agent — type 'quit' or Ctrl-C to exit.")
        try:
            while True:
                q = input("\n> ").strip()
                if q.lower() in {"quit", "exit"}:
                    return 0
                if not q:
                    continue
                result = run_query(graph, q)
                render_terminal(q, result, show_trace=args.trace)
        except (EOFError, KeyboardInterrupt):
            return 0

    query = args.query or "What are the prerequisites for CS-301 Artificial Intelligence?"
    result = run_query(graph, query)
    if args.json:
        print(json.dumps(to_json(query, result), indent=2))
    else:
        render_terminal(query, result, show_trace=args.trace or True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
