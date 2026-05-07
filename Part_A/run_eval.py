"""
Lab 7 / Lab 10: Evaluation Pipeline — CI-Ready
================================================
Runs the agent through a test dataset and scores responses using
LLM-as-a-Judge for Faithfulness, Answer Relevancy, and Tool Call Accuracy.

CI behaviour:
  exit 0  — all metric scores meet or exceed their thresholds (PASS)
  exit 1  — one or more metric scores fall below threshold (FAIL)

All credentials are read from environment variables:
  GROQ_API_KEY        required — Groq LLM inference
  LANGSMITH_API_KEY   optional — trace observability
  LANGCHAIN_PROJECT   optional — LangSmith project name

Threshold configuration: eval_thresholds.json (committed to version control).
Results written to:       evaluation_results.json (machine-readable JSON).

Usage:
  python run_eval.py                # full dataset
  python run_eval.py --max 5        # limit to 5 cases (faster CI run)
  python run_eval.py --quiet        # suppress per-query output
"""

import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from langchain_core.messages import AIMessage, HumanMessage
from langchain_groq import ChatGroq

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    LANGSMITH_API_KEY,
    enable_langsmith,
)

# ─── LangSmith (optional — silently skipped when key absent) ─────────────────

langsmith_enabled = enable_langsmith()
_langsmith_client = None

if langsmith_enabled:
    try:
        from langsmith import Client as LangSmithClient
        _langsmith_client = LangSmithClient()
    except Exception:
        langsmith_enabled = False


# ─── Paths ───────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(__file__)

# eval_thresholds.json is the versioned CI threshold file (Lab 10 checklist item)
THRESHOLDS_PATH  = os.path.join(_HERE, "eval_thresholds.json")
# eval_threshold_config.json is the older Lab 7 config — used as fallback
THRESHOLDS_LEGACY = os.path.join(_HERE, "eval_threshold_config.json")

TEST_DATASET_PATH = os.path.join(_HERE, "test_dataset.json")
EVAL_REPORT_PATH  = os.path.join(_HERE, "evaluation_results.json")


# ─── Threshold Loading ────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "min_faithfulness": 0.80,
    "min_relevancy":    0.85,
    "min_tool_accuracy": 0.80,
}


def load_thresholds() -> dict:
    """Load thresholds from eval_thresholds.json (preferred) or legacy file."""
    # New versioned file (Lab 10)
    if os.path.exists(THRESHOLDS_PATH):
        with open(THRESHOLDS_PATH) as f:
            data = json.load(f)
        # eval_thresholds.json stores thresholds as a list under "thresholds"
        if "thresholds" in data:
            return {t["metric"]: t["threshold"] for t in data["thresholds"]}
        return data  # plain dict fallback

    # Legacy Lab 7 file
    if os.path.exists(THRESHOLDS_LEGACY):
        with open(THRESHOLDS_LEGACY) as f:
            return json.load(f)

    return DEFAULT_THRESHOLDS


def load_test_dataset() -> list:
    with open(TEST_DATASET_PATH) as f:
        return json.load(f)


# ─── LangSmith Helpers ────────────────────────────────────────────────────────

def _get_langsmith_trace_url(run_id: str) -> str:
    from config import LANGSMITH_PROJECT
    return f"https://smith.langchain.com/o/default/projects/p/{LANGSMITH_PROJECT}/r/{run_id}"


def _get_recent_run_id() -> str:
    if not _langsmith_client:
        return ""
    try:
        from config import LANGSMITH_PROJECT
        runs = list(_langsmith_client.list_runs(project_name=LANGSMITH_PROJECT, limit=1))
        return str(runs[0].id) if runs else ""
    except Exception:
        return ""


def _get_run_trace_details(run_id: str) -> dict:
    if not _langsmith_client or not run_id:
        return {}
    try:
        run = _langsmith_client.read_run(run_id)
        children = list(_langsmith_client.list_runs(
            project_name=getattr(run, "session_name", ""),
            filter=f'eq(parent_run_id, "{run_id}")',
        ))
        nodes = []
        total_tokens = 0
        for c in children:
            ms = 0
            if c.end_time and c.start_time:
                ms = round((c.end_time - c.start_time).total_seconds() * 1000)
            tok = getattr(c, "total_tokens", 0) or 0
            total_tokens += tok
            nodes.append({"name": c.name, "type": c.run_type,
                          "duration_ms": ms, "tokens": tok, "status": c.status})
        total_ms = 0
        if run.end_time and run.start_time:
            total_ms = round((run.end_time - run.start_time).total_seconds() * 1000)
        return {"run_id": run_id, "total_duration_ms": total_ms,
                "total_tokens": total_tokens, "status": run.status, "nodes": nodes}
    except Exception as e:
        return {"run_id": run_id, "error": str(e)}


# ─── Agent Runner ─────────────────────────────────────────────────────────────

def run_agent_query(query: str) -> dict:
    """Invoke the agent for a single query and return structured results."""
    from graph import build_react_graph

    graph = build_react_graph()
    t0 = time.time()
    result = graph.invoke({"messages": [HumanMessage(content=query)]})
    latency_ms = round((time.time() - t0) * 1000)

    answer = ""
    tools_called: list[str] = []
    contexts: list[str] = []
    trace: list[dict] = []

    for msg in result["messages"]:
        if isinstance(msg, HumanMessage):
            trace.append({"type": "user", "content": msg.content})
        elif isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tools_called.append(tc["name"])
                trace.append({"type": "tool_call", "tool": tc["name"], "args": tc["args"]})
            if msg.content:
                trace.append({"type": "thought", "content": msg.content[:300]})
        elif hasattr(msg, "name") and msg.name:
            contexts.append((msg.content or "")[:500])
            trace.append({"type": "tool_result", "tool": msg.name,
                          "content": (msg.content or "")[:200]})
        elif isinstance(msg, AIMessage) and msg.content:
            answer = msg.content
            trace.append({"type": "answer", "content": msg.content[:500]})

    ls_run_id = ls_url = ""
    ls_trace: dict = {}
    if langsmith_enabled:
        time.sleep(0.5)
        ls_run_id = _get_recent_run_id()
        if ls_run_id:
            ls_url   = _get_langsmith_trace_url(ls_run_id)
            ls_trace = _get_run_trace_details(ls_run_id)

    return {
        "answer": answer, "tools_called": tools_called,
        "contexts": contexts, "latency_ms": latency_ms, "trace": trace,
        "langsmith_run_id": ls_run_id, "langsmith_url": ls_url,
        "langsmith_trace": ls_trace,
    }


# ─── LLM-as-a-Judge Scoring ──────────────────────────────────────────────────

def _judge_llm() -> "ChatGroq":
    return ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0.0)


def score_faithfulness(answer: str, contexts: list[str]) -> float:
    if not answer or not contexts:
        return 0.0
    ctx = "\n---\n".join(contexts[:5])
    prompt = (
        "You are an evaluation judge. Score how FAITHFUL the answer is to the context.\n"
        "Faithfulness = only claims supported by the context, no hallucinations.\n\n"
        f"Context:\n{ctx}\n\nAnswer:\n{answer}\n\n"
        "Respond with ONLY a decimal 0.0–1.0."
    )
    try:
        r = _judge_llm().invoke([HumanMessage(content=prompt)])
        return max(0.0, min(1.0, float(r.content.strip())))
    except Exception:
        return 0.5


def score_relevancy(answer: str, query: str) -> float:
    if not answer:
        return 0.0
    prompt = (
        "You are an evaluation judge. Score how RELEVANT the answer is to the query.\n"
        "Relevancy = the answer directly addresses what was asked.\n\n"
        f"Query:\n{query}\n\nAnswer:\n{answer}\n\n"
        "Respond with ONLY a decimal 0.0–1.0."
    )
    try:
        r = _judge_llm().invoke([HumanMessage(content=prompt)])
        return max(0.0, min(1.0, float(r.content.strip())))
    except Exception:
        return 0.5


def score_tool_accuracy(tools_called: list[str], required_tool: str) -> float:
    if required_tool == "multiple":
        return 1.0 if len(set(tools_called)) >= 2 else 0.0
    return 1.0 if required_tool in tools_called else 0.0


# ─── Evaluation Pipeline ──────────────────────────────────────────────────────

def run_evaluation(max_queries: int | None = None, verbose: bool = True) -> dict:
    """Run the full evaluation pipeline and write evaluation_results.json.

    Returns a report dict.  Exit code is set by the caller.
    """
    dataset   = load_test_dataset()
    thresholds = load_thresholds()

    if max_queries:
        dataset = dataset[:max_queries]

    if verbose:
        print("=" * 70)
        print("EVALUATION PIPELINE")
        print(f"  Cases     : {len(dataset)}")
        print(f"  Thresholds: faithfulness>={thresholds.get('min_faithfulness', 0.80)}"
              f"  relevancy>={thresholds.get('min_relevancy', 0.85)}"
              f"  tool_accuracy>={thresholds.get('min_tool_accuracy', 0.80)}")
        print(f"  LangSmith : {'ENABLED' if langsmith_enabled else 'DISABLED'}")
        print("=" * 70)

    results: list[dict] = []
    total_f = total_r = total_t = total_lat = 0.0

    for i, tc in enumerate(dataset):
        query        = tc["query"]
        required_tool = tc["required_tool"]

        if verbose:
            print(f"\n[{i+1}/{len(dataset)}] {query[:80]}...")

        try:
            ar = run_agent_query(query)
            f  = score_faithfulness(ar["answer"], ar["contexts"])
            r  = score_relevancy(ar["answer"], query)
            t  = score_tool_accuracy(ar["tools_called"], required_tool)

            row = {
                "id": tc["id"], "query": query,
                "expected_answer":  tc["expected_answer"],
                "agent_answer":     ar["answer"][:500],
                "tools_called":     ar["tools_called"],
                "required_tool":    required_tool,
                "faithfulness":     f, "relevancy": r, "tool_accuracy": t,
                "latency_ms":       ar["latency_ms"],
                "category":         tc["category"],
                "langsmith_run_id": ar.get("langsmith_run_id", ""),
                "langsmith_url":    ar.get("langsmith_url", ""),
                "langsmith_trace":  ar.get("langsmith_trace", {}),
            }
            results.append(row)
            total_f   += f
            total_r   += r
            total_t   += t
            total_lat += ar["latency_ms"]

            if verbose:
                suffix = f" | trace: {ar['langsmith_url']}" if ar.get("langsmith_url") else ""
                print(f"  F={f:.2f}  R={r:.2f}  T={t:.2f}  {ar['latency_ms']}ms{suffix}")

        except Exception as exc:
            if verbose:
                print(f"  [ERROR] {str(exc)[:120]}")
            results.append({
                "id": tc["id"], "query": query,
                "error": str(exc)[:200],
                "faithfulness": 0.0, "relevancy": 0.0, "tool_accuracy": 0.0,
                "latency_ms": 0, "category": tc["category"],
            })

    n = max(len(results), 1)
    avg_f   = round(total_f   / n, 3)
    avg_r   = round(total_r   / n, 3)
    avg_t   = round(total_t   / n, 3)
    avg_lat = round(total_lat / n)

    # Per-category breakdown
    cats: dict = {}
    for row in results:
        cat = row.get("category", "unknown")
        cats.setdefault(cat, {"f": [], "r": [], "t": [], "lat": []})
        cats[cat]["f"].append(row.get("faithfulness", 0))
        cats[cat]["r"].append(row.get("relevancy", 0))
        cats[cat]["t"].append(row.get("tool_accuracy", 0))
        cats[cat]["lat"].append(row.get("latency_ms", 0))

    category_breakdown = {}
    for cat, s in cats.items():
        cn = max(len(s["f"]), 1)
        category_breakdown[cat] = {
            "count": cn,
            "avg_faithfulness":  round(sum(s["f"])  / cn, 3),
            "avg_relevancy":     round(sum(s["r"])  / cn, 3),
            "avg_tool_accuracy": round(sum(s["t"])  / cn, 3),
            "avg_latency_ms":    round(sum(s["lat"]) / cn),
        }

    min_f = thresholds.get("min_faithfulness", 0.80)
    min_r = thresholds.get("min_relevancy",    0.85)
    min_t = thresholds.get("min_tool_accuracy", 0.80)

    # Machine-readable per-metric pass/fail (CI checklist requirement)
    metric_results = [
        {"metric": "faithfulness",  "score": avg_f, "threshold": min_f, "passed": avg_f >= min_f},
        {"metric": "relevancy",     "score": avg_r, "threshold": min_r, "passed": avg_r >= min_r},
        {"metric": "tool_accuracy", "score": avg_t, "threshold": min_t, "passed": avg_t >= min_t},
    ]

    passed = all(m["passed"] for m in metric_results)

    ls_urls = [row["langsmith_url"] for row in results if row.get("langsmith_url")]

    report = {
        "timestamp":        datetime.now().isoformat(),
        "total_test_cases": len(dataset),
        "evaluated":        len(results),
        "thresholds":       {"min_faithfulness": min_f, "min_relevancy": min_r,
                             "min_tool_accuracy": min_t},
        "aggregate_scores": {
            "avg_faithfulness": avg_f, "avg_relevancy": avg_r,
            "avg_tool_accuracy": avg_t, "avg_latency_ms": avg_lat,
        },
        "metric_results":      metric_results,   # machine-readable per-metric CI output
        "category_breakdown":  category_breakdown,
        "passed":              passed,
        "langsmith_enabled":   langsmith_enabled,
        "langsmith_traces_captured": len(ls_urls),
        "per_query_results":   results,
    }

    with open(EVAL_REPORT_PATH, "w") as f_out:
        json.dump(report, f_out, indent=2)

    if verbose:
        print("\n" + "=" * 70)
        print("EVALUATION SUMMARY")
        print("=" * 70)
        for m in metric_results:
            status = "PASS" if m["passed"] else "FAIL"
            print(f"  [{status}] {m['metric']:<15}: {m['score']:.3f}  (threshold >= {m['threshold']})")
        print(f"  Avg latency : {avg_lat} ms")
        print(f"  Overall     : {'PASS' if passed else 'FAIL'}")
        if ls_urls:
            print(f"  Sample trace: {ls_urls[0]}")
        print(f"  Report saved: {EVAL_REPORT_PATH}")
        print("=" * 70)

    return report


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="CI-ready evaluation pipeline for the Inventory Reorder Agent"
    )
    parser.add_argument("--max",   type=int,  default=None,
                        help="Maximum number of test cases to evaluate")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-query output (CI-friendly)")
    args = parser.parse_args()

    # Fail fast with a clear message if the key is missing — no hardcoded fallback
    if not GROQ_API_KEY:
        print(
            "[CI ERROR] GROQ_API_KEY environment variable is not set.\n"
            "  Store it in GitHub Secrets (CI) or export it locally.",
            file=sys.stderr,
        )
        sys.exit(1)

    report = run_evaluation(max_queries=args.max, verbose=not args.quiet)

    if report["passed"]:
        if not args.quiet:
            print("\n[CI] EXIT 0 — All metrics above threshold. Build PASSES.")
        sys.exit(0)
    else:
        if not args.quiet:
            print("\n[CI] EXIT 1 — One or more metrics below threshold. Build FAILS.")
        sys.exit(1)
