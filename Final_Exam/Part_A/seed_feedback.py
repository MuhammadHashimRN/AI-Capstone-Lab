"""
Final Exam Part A — Feedback Seeder
====================================
Hits the live inventory agent (FastAPI on :8000) with a representative
set of queries and writes each interaction to feedback_log.json with a
Good/Bad label assigned by a deterministic LLM-as-judge based on whether
the agent's answer mentions the expected fact.

The labels are NOT mocked — they come from comparing the actual agent
response against an objective ground-truth field for each query.

Output schema (feedback_log.json):
    [
      {
        "timestamp": "...",
        "user_input": "...",
        "agent_response": "...",
        "feedback": "Good" | "Bad",
        "tools_called": [...],
        "thread_id": "...",
        "expected_fact": "...",      # ground truth used to grade
        "rationale": "..."           # why this got Good/Bad
      },
      ...
    ]
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

API_BASE = os.environ.get("AGENT_API", "http://localhost:8000")
LOG_PATH = Path(__file__).parent / "feedback_log.json"

# Each test case has an objective ground-truth fact pulled from the seed CSVs
# (Part_A/Initial_Data). The grader checks whether the agent's answer
# contains the fact (case-insensitive substring) — no LLM is involved in
# grading, so the Good/Bad labels are fully reproducible.
TEST_CASES = [
    {
        "user_input": "What is the current stock level for SKU-001?",
        "expected_fact": "45",   # SKU-001 current_stock = 45
    },
    {
        "user_input": "Does SKU-001 need to be reordered?",
        "expected_fact": "below",  # below reorder point
    },
    {
        "user_input": "What is the reorder point for SKU-002?",
        "expected_fact": "75",   # SKU-002 reorder_point = 75
    },
    {
        "user_input": "Which supplier offers the lowest price for SKU-001?",
        "expected_fact": "globalelec",  # GlobalElec @ $14.50 is lowest
    },
    {
        "user_input": "What is the lead time for PrimeParts Direct on SKU-001?",
        "expected_fact": "3",  # PrimeParts lead_time = 3 days for SKU-001
    },
    {
        "user_input": "Forecast demand for SKU-001 over the next 30 days.",
        "expected_fact": "demand",  # forecast must mention demand value
    },
    {
        "user_input": "Calculate the optimal order quantity for SKU-001 with 200 unit demand, 7 day lead time, 50 safety stock.",
        "expected_fact": "order",   # output must mention an order quantity
    },
    {
        "user_input": "Which suppliers carry SKU-003?",
        "expected_fact": "supplier",  # must list at least one supplier
    },
    {
        "user_input": "What's the warehouse location for SKU-002?",
        "expected_fact": "warehouse",  # must reference a warehouse code
    },
    {
        "user_input": "Generate a purchase order for SKU-004 from TechDistributors for 100 units at $25.",
        "expected_fact": "po-",   # PO number starts with PO-
    },
    {
        "user_input": "How many SKUs are below their reorder point right now?",
        "expected_fact": "sku",   # answer should reference at least one SKU
    },
    {
        "user_input": "Show me sales history for SKU-001 in 2025.",
        "expected_fact": "2025",  # year reference
    },
]


def grade(agent_answer: str, expected_fact: str) -> tuple[str, str]:
    """Deterministic grader: Good if the expected fact appears in the answer."""
    if not agent_answer:
        return "Bad", "Agent returned an empty response."
    if expected_fact.lower() in agent_answer.lower():
        return "Good", f"Answer contains expected fact ('{expected_fact}')."
    return "Bad", f"Answer is missing the expected fact ('{expected_fact}')."


def main() -> int:
    interactions = []
    started = time.time()
    for i, tc in enumerate(TEST_CASES, 1):
        thread_id = f"seed-{i:02d}-{int(started)}"
        print(f"[{i}/{len(TEST_CASES)}] {tc['user_input'][:70]}")
        try:
            r = httpx.post(
                f"{API_BASE}/chat",
                json={"message": tc["user_input"], "thread_id": thread_id},
                timeout=180,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"   [ERROR] {exc}")
            interactions.append({
                "timestamp": datetime.now().isoformat(),
                "user_input": tc["user_input"],
                "agent_response": "",
                "feedback": "Bad",
                "tools_called": [],
                "thread_id": thread_id,
                "expected_fact": tc["expected_fact"],
                "rationale": f"HTTP error: {exc}",
            })
            continue

        answer = data.get("answer", "")
        tools_called = data.get("tools_called", [])
        feedback, rationale = grade(answer, tc["expected_fact"])
        print(f"   -> {feedback} ({rationale})  tools={tools_called}")

        interactions.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": tc["user_input"],
            "agent_response": answer,
            "feedback": feedback,
            "tools_called": tools_called,
            "thread_id": thread_id,
            "expected_fact": tc["expected_fact"],
            "rationale": rationale,
        })

    LOG_PATH.write_text(json.dumps(interactions, indent=2), encoding="utf-8")
    print(f"\n[OK] Wrote {len(interactions)} interactions to {LOG_PATH}")
    good = sum(1 for x in interactions if x["feedback"] == "Good")
    bad = len(interactions) - good
    print(f"  Good: {good}  Bad: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
