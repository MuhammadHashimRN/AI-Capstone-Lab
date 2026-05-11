# Improvement Demo — Part A

This document shows one concrete defect identified from the feedback log,
the fix that was applied, and the agent's behaviour on the *same* query
before and after the fix. Both responses are produced by the live FastAPI
service (`POST /chat`) — no mocks.

---

## 1. Issue Identified

> **The agent answers "lowest price" / "cheapest supplier" questions with
> the multi-criteria optimum instead of the literal minimum.**

When a user asks for the literal cheapest supplier, the agent invokes
`select_best_supplier`, which scores suppliers on a weighted blend of
**Price (40%) + Lead Time (25%) + Reliability (20%) + Quality (15%)**.
The "best" supplier under that weighting is frequently *not* the one with
the lowest unit price.

This was discovered from a real interaction in `feedback_log.json`:

| Query | Agent Tools | Agent Answer | Verdict |
|-------|-------------|--------------|---------|
| Which supplier offers the lowest price for SKU-001? | `query_all_suppliers`, `select_best_supplier` | "PrimeParts Direct with a unit price of $14.72" | **Bad** — actual cheapest is GlobalElec at $14.50 |

The same root cause produces a second observed failure: when the user
provides explicit parameters to `generate_purchase_order`, the agent
*re-derives* them by running forecasting and supplier scoring, then
generates a PO using its own values instead of the user's. Both failures
share the pattern **"the agent over-reasons and overrides explicit user
intent."**

---

## 2. Fix Applied

The system prompt in [`secured_graph.py`](../../Part_A/secured_graph.py) was
extended with explicit **user-intent rules**:

```
USER-INTENT RULES (Final-Exam Part A improvement):
- When the user asks for a *literal extreme* — "lowest price", "cheapest",
  "highest reliability", "shortest lead time", etc. — use
  `query_all_suppliers` and answer directly by sorting on the requested
  field. Do NOT call `select_best_supplier`; that tool returns the
  multi-criteria optimum, not the literal minimum/maximum, and will
  surface a different supplier.
- When the user supplies explicit parameters to `generate_purchase_order`
  (sku, supplier_name, quantity, unit_price), invoke that tool DIRECTLY
  with the user's values. Do NOT re-run forecasting, supplier scoring, or
  EOQ — the user has already made those decisions.
```

The FastAPI server was restarted to pick up the new prompt. No tool code,
graph structure, or guardrail logic was changed — the fix is a pure prompt
intervention.

---

## 3. Before vs After — Same Queries, Live Service

### Query A — "Which supplier offers the lowest price for SKU-001?"

| | Before fix | After fix |
|---|---|---|
| **Tools called** | `query_all_suppliers`, `select_best_supplier` | `query_all_suppliers` (×3, one per supplier catalog) |
| **Agent answer** | *"The recommended supplier for SKU-001 is PrimeParts Direct with a unit price of $14.72."* | *"The supplier with the lowest price for SKU-001 is GlobalElec Supply with a unit price of $14.5."* |
| **Correct?** | ❌ PrimeParts list price is $16.00; the $14.72 figure is the multi-criteria-weighted value, not a real catalog price | ✅ GlobalElec @ $14.50 is the actual lowest list price |

### Query B — "Generate a purchase order for SKU-004 from TechDistributors for 100 units at $25."

| | Before fix | After fix |
|---|---|---|
| **Tools called** | `generate_purchase_order`, `query_all_suppliers`, `select_best_supplier`, `calculate_order_quantity`, `get_current_inventory`, `get_sales_data`, `forecast_demand` (**7 tools**) | `generate_purchase_order` (**1 tool**) |
| **Agent answer** | *"The optimal supplier selected is PrimeParts Direct, with a unit price of $34.96... optimal order quantity calculated using the EOQ model is 129 units..."* (overrode user) | *"I apologize, but I cannot provide the output as it contains a file path and internal metadata."* (sanitiser stripped the PO path; tool ran directly with user's exact params) |
| **Respected user intent?** | ❌ Replaced supplier (TechDist → PrimeParts), quantity (100 → 129), price ($25 → $34.96) | ✅ Called `generate_purchase_order` once with user's values |

Query B's "after" response is empty because the output sanitiser in
`guardrails_config.py` redacts the PO file path. That's a separate
follow-up (loosen the sanitiser regex for `purchase_orders/`-relative
paths), not the issue we set out to fix here. The behavioural win is
clear from the tool list: 7 tool calls collapsed to 1.

---

## 4. Reproduction Commands

```bash
# 1. Run the live agent at :8000 (uvicorn main:app …)
# 2. Capture BEFORE behaviour with the original prompt:
curl -sS -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"Which supplier offers the lowest price for SKU-001?","thread_id":"before"}'
# 3. Edit Part_A/secured_graph.py — append the USER-INTENT RULES block.
# 4. Restart uvicorn.
# 5. Capture AFTER behaviour:
curl -sS -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"Which supplier offers the lowest price for SKU-001?","thread_id":"after"}'
```

The exact responses captured during this exercise are saved in
[`feedback_log.json`](feedback_log.json) (BEFORE) and live in the FastAPI
service for the AFTER run.
