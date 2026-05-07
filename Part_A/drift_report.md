# Lab 11: Drift Report — Dynamic Inventory Reorder Agent

**Generated:** 2026-05-05  
**Analysis window:** Last 15 interactions (May 5 – April 21, 2026)  
**Tool:** `analyze_feedback.py`

---

## 1. Overall Satisfaction

| Metric | Value |
|---|---|
| Total interactions logged | 15 |
| Thumbs up (+1) | 9 (60%) |
| Neutral (0) | 2 (13%) |
| Thumbs down (−1) | 4 (27%) |
| **Satisfaction rate** | **60%** |

A 60% satisfaction rate is below the target of 85%. The agent needs improvement in three areas: hallucination reduction, tool routing accuracy, and response conciseness.

---

## 2. Failure Breakdown

| Category | Count | % of Failures |
|---|---|---|
| **Hallucination** | 3 | 50% |
| **Tool Error** | 2 | 33% |
| **Wrong Tone** | 2 | 33% |

### 2.1 Hallucination (50% of failures)

The agent fabricated facts not present in the knowledge base:

| Query | Fabricated Claim | Actual Truth |
|---|---|---|
| "Does GlobalElec offer seasonal discounts?" | "15% holiday discount exists" | No such discount in supplier catalog |
| "How long does PrimeParts deliver SKU-003?" | "3 business days" | Catalog states 7 days |
| "Is there a promotion this week?" | "Back to School promotion, 20% boost" | No active promotion this week |

**Root cause:** The LLM reasoning node answers from parametric memory when the retrieved context is ambiguous or absent. The RAG grounding is not being enforced strictly enough.

### 2.2 Tool Error (33% of failures)

The agent called the wrong tool or skipped mandatory steps:

| Query | Expected Behavior | Actual Behavior |
|---|---|---|
| "Generate PO for SKU-001, 200 units" | Call `generate_purchase_order` | Called `query_knowledge_base` instead |
| "Reorder SKU-002 if needed" | Check inventory first, then PO | Generated PO without inventory check |

**Root cause:** The system prompt does not enforce the step order strictly. The agent sometimes short-circuits to the final action without completing prerequisite analysis steps.

### 2.3 Wrong Tone (33% of failures)

The agent produced overly verbose or overly technical answers:

| Query | Issue |
|---|---|
| "Should I reorder SKU-002?" | Showed raw EOQ formula instead of a plain recommendation |
| "How many suppliers do we have for SKU-003?" | 500-word essay instead of "3 suppliers" |

**Root cause:** The system prompt does not specify response length guidelines or audience calibration. The agent defaults to maximum-information responses regardless of query complexity.

---

## 3. Drift Analysis

| Period | Satisfaction Rate |
|---|---|
| Previous 7 days (Apr 22–28) | 50% (3/6 positive) |
| Recent 7 days (Apr 29–May 5) | 67% (6/9 positive) |
| **Trend** | **+17% (improving)** |

The recent improvement is encouraging but the absolute rate (67%) is still below the 85% target. The hallucination issues are concentrated in the earlier period; the more recent failures are primarily tone-related.

---

## 4. Identified Drift Signals

1. **Hallucination cluster** in weeks 2–3: Three back-to-back hallucination failures suggest the RAG context retrieval degraded when querying about promotions and lead times. The `query_knowledge_base` tool may not have been called before the agent answered.

2. **Tool routing regression**: Two sequential tool-error failures (days 10 and 5) where the agent either called the wrong tool or skipped mandatory preconditions. This suggests the step-enforcement logic in the prompt is weakening.

3. **Tone complaints in recent interactions**: The two wrong-tone failures occurred in the last 3 days, suggesting the agent is reverting to verbose output for simple queries as conversation context grows.

---

## 5. Recommended Prompt Improvements

See `improved_prompt.txt` for the updated system prompt. Key changes:

1. **Explicit grounding instruction** — "Never state a fact unless it was returned by a tool. If you are unsure, call `query_knowledge_base` before answering."
2. **Enforced step order** — Numbered precondition list with explicit "DO NOT skip steps" warning.
3. **Conciseness rule** — "For simple factual queries (a single number or yes/no), respond in 1–2 sentences maximum."
4. **Tool routing clarification** — Explicit table mapping query types to required tools.

---

## 6. Recommended Data Collection Improvements

- Capture `message_id` per turn (not per session) to enable per-step failure attribution.
- Add a `category` field that users can fill in from a dropdown (reduces free-text categorization errors).
- Log the tools called per response to correlate tool errors with user complaints automatically.
- Target: collect 50 feedback records per week to achieve statistically significant drift detection.
