"""
Final Exam Part B — Test Harness
=================================
Runs the 5 required Self-RAG scenarios end-to-end and writes
both a JSON trace and a markdown evaluation report.

Scenarios:
  1. No retrieval needed       (greeting / general knowledge)
  2. Retrieval, docs relevant  (specific course info)
  3. Retrieval, docs irrelevant -> web fallback
  4. Hallucination retry       (engineered to trip the self-check)
  5. Creative case             (faculty lookup combining catalog + directory)
  6. Bonus: policy lookup      (GPA / fees)

For each case we record: scenario name, query, expected path, actual
trace, final answer, retrieval decision, doc grades, web fallback flag,
retry count, hallucination check, latency.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from graph import build_self_rag_graph
from self_rag_agent import run_query, to_json

TEST_CASES = [
    {
        "id": 1,
        "scenario": "Retrieval NOT needed (greeting)",
        "query": "Hi there! How are you today?",
        "expected_path": "route_query -> direct_answer -> END (no retrieval, no grading)",
        "expected_behavior": "Agent should classify as NO_RETRIEVE and produce a short conversational reply.",
    },
    {
        "id": 2,
        "scenario": "Retrieval needed, documents relevant",
        "query": "What are the prerequisites and credit hours for CS-301 Artificial Intelligence?",
        "expected_path": "route_query -> retrieve -> grade -> generate -> hallucination_check -> finalize",
        "expected_behavior": "Agent should retrieve the CS-301 chunk, mark only that doc relevant, and answer with the correct prereqs (CS-102, MATH-201) and credit hours (3).",
    },
    {
        "id": 3,
        "scenario": "Retrieval needed but docs irrelevant -> web fallback",
        # Hostel/housing is a topic students obviously ask about (router
        # will classify as university-specific RETRIEVE), but NONE of the 5
        # PDFs cover student housing, dorms, or accommodation. Every
        # retrieved chunk should be tangential at best — the grader should
        # mark all as NO and the agent should fall through to web search.
        "query": "Where on the XYZ National University campus is the official on-campus student hostel located and how do I apply for a room?",
        "expected_path": "route_query -> retrieve -> grade (all irrelevant) -> web_search -> generate -> hallucination_check -> finalize",
        "expected_behavior": "The KB has no housing info, so all retrieved docs should be graded NO; the agent must fall back to web search.",
    },
    {
        "id": 4,
        "scenario": "Hallucination self-check retry",
        # The CS-301 AI catalog entry lists prereqs/credits/instructor but
        # does NOT name a textbook. The model is tempted to volunteer the
        # standard AI textbook ("Russell & Norvig"). The hallucination
        # checker should compare the answer against the chunk and detect
        # the unsupported claim, triggering a regenerate.
        "query": "Which specific textbook (give title, author, and edition) is the required reading for CS-301 Artificial Intelligence at XYZ National University?",
        "expected_path": "route_query -> retrieve -> grade -> generate -> hallucination_check (likely NO on attempt 1) -> generate (retry) -> hallucination_check -> finalize",
        "expected_behavior": "The CS-301 chunk is retrieved and graded relevant, but it does not list a textbook. If the model invents Russell & Norvig (a common training-data answer), the self-check should detect the unsupported claim and trigger a retry — eventually finalizing with either a disclaimer or a grounded ‘textbook not listed in the catalog’ answer.",
    },
    {
        "id": 5,
        "scenario": "Creative case — faculty + course lookup",
        "query": "Which professor in the Electrical Engineering department teaches Signals & Systems, and what is their office number?",
        "expected_path": "route_query -> retrieve -> grade -> generate -> hallucination_check -> finalize",
        "expected_behavior": "The agent must combine the EE catalog (course -> instructor name) and the faculty directory (instructor -> office) to answer.",
    },
    {
        "id": 6,
        "scenario": "Policy lookup (bonus)",
        "query": "What is the late registration fee and the minimum CGPA required to graduate?",
        "expected_path": "route_query -> retrieve -> grade -> generate -> hallucination_check -> finalize",
        "expected_behavior": "Agent should pull the relevant policy chunks (PKR 5000 late fee, 2.00 CGPA minimum) and answer both facts.",
    },
]


def main() -> int:
    if not os.environ.get("GROQ_API_KEY"):
        print("[ERROR] GROQ_API_KEY not set.", file=sys.stderr)
        return 1

    graph = build_self_rag_graph()
    results: list[dict] = []

    for tc in TEST_CASES:
        print(f"\n[{tc['id']}] {tc['scenario']}")
        print(f"    Q: {tc['query'][:90]}")
        t0 = time.time()
        try:
            state = run_query(graph, tc["query"])
            trim = to_json(tc["query"], state)
            ok = True
        except Exception as exc:
            trim = {"error": str(exc)}
            ok = False
        elapsed = round((time.time() - t0) * 1000)
        print(f"    -> {'ok' if ok else 'ERROR'}  ({elapsed} ms)")
        results.append({
            "id": tc["id"],
            "scenario": tc["scenario"],
            "query": tc["query"],
            "expected_path": tc["expected_path"],
            "expected_behavior": tc["expected_behavior"],
            "result": trim,
            "elapsed_ms": elapsed,
        })

    # Persist machine-readable traces
    traces_path = HERE / "test_traces.json"
    traces_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[OK] Wrote {len(results)} traces to {traces_path}")

    # Build evaluation_results.md
    lines: list[str] = []
    lines.append("# Self-RAG Evaluation Results")
    lines.append("")
    lines.append("_Auto-generated by `run_tests.py` — each section is a real run of "
                 "the Self-RAG graph against the provided knowledge base. Traces are "
                 "captured directly from LangGraph state._")
    lines.append("")

    for r in results:
        out = r["result"]
        lines.append(f"## Test Case {r['id']}: {r['scenario']}")
        lines.append("")
        lines.append(f"**Query**:")
        lines.append("")
        lines.append(f"> {r['query']}")
        lines.append("")
        lines.append(f"**Expected path**: `{r['expected_path']}`")
        lines.append("")
        lines.append(f"**Expected behavior**: {r['expected_behavior']}")
        lines.append("")
        if "error" in out:
            lines.append(f"**ERROR**: `{out['error']}`")
            lines.append("")
            continue

        lines.append("**Decision Trace** (actual):")
        lines.append("")
        lines.append("```")
        for step in out.get("decision_trace", []):
            lines.append(step)
        lines.append("```")
        lines.append("")
        lines.append(f"- `needs_retrieval` = `{out['needs_retrieval']}`  "
                     f"(reason: {out.get('retrieval_reasoning','').strip()})")
        lines.append(f"- `retrieved_doc_count` = `{out['retrieved_doc_count']}`,  "
                     f"`graded_doc_count` = `{out['graded_doc_count']}`")
        lines.append(f"- `used_web_fallback` = `{out['used_web_fallback']}`,  "
                     f"`web_result_count` = `{out['web_result_count']}`")
        lines.append(f"- `retry_count` = `{out['retry_count']}`,  "
                     f"`hallucination_grounded` = `{out['hallucination_grounded']}`")
        lines.append(f"- `latency_ms` = `{out['latency_ms']}`")
        if out.get("graded_doc_metadata"):
            lines.append("- relevant chunk sources:")
            for m in out["graded_doc_metadata"]:
                lines.append(f"  - `{m.get('source_file','?')}` :: "
                             f"`{m.get('section_title','?')}`")
        lines.append("")
        lines.append("**Final Answer**:")
        lines.append("")
        lines.append("> " + out["final_answer"].replace("\n", "\n> "))
        lines.append("")
        lines.append("---")
        lines.append("")

    md_path = HERE / "evaluation_results.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote evaluation_results.md ({md_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
