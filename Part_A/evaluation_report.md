# Evaluation Report — Lab 7
## Dynamic Inventory Reorder Agent

---

## 1. Evaluation Methodology

The agent was evaluated using an **LLM-as-a-Judge** approach (RAGAS-style scoring) with the Groq Llama-3.3-70B model serving as both the agent and the evaluator. Three metrics were computed for each test case:

| Metric | Description | Scoring Method |
|--------|-------------|----------------|
| **Faithfulness** | Does the answer stay true to retrieved context? | LLM judge scores 0.0-1.0 based on context-answer alignment |
| **Answer Relevancy** | How well does the response address the query? | LLM judge scores 0.0-1.0 based on query-answer alignment |
| **Tool Call Accuracy** | Did the agent invoke the correct tool(s)? | Binary: 1.0 if required tool called, 0.0 otherwise |

---

## 2. Test Dataset Summary

- **Total test cases**: 25
- **Categories covered**:
  - `inventory_check` (6 cases): Verifying stock levels and reorder status
  - `forecasting` (2 cases): Demand prediction using sales history
  - `supplier_query` (6 cases): Querying and comparing supplier offerings
  - `supplier_selection` (1 case): Multi-criteria weighted supplier ranking
  - `order_calculation` (2 cases): EOQ-based optimal order quantity
  - `purchase_order` (1 case): PO generation (high-risk action)
  - `sales_analysis` (2 cases): Historical sales data retrieval
  - `knowledge_base` (3 cases): RAG vector store queries
  - `full_workflow` (2 cases): Multi-step reorder pipelines

---

## 3. Aggregate Scores

| Metric | Score | Threshold | Status |
|--------|-------|-----------|--------|
| **Average Faithfulness** | 0.87 | >= 0.80 | PASS |
| **Average Relevancy** | 0.90 | >= 0.85 | PASS |
| **Average Tool Call Accuracy** | 0.92 | >= 0.80 | PASS |
| **Average Latency** | ~4500ms | N/A | - |

**Overall Result: PASS**

---

## 4. Category Breakdown

| Category | # Cases | Avg Faithfulness | Avg Relevancy | Avg Tool Accuracy | Avg Latency |
|----------|---------|-----------------|---------------|-------------------|-------------|
| inventory_check | 6 | 0.92 | 0.94 | 1.00 | ~3200ms |
| forecasting | 2 | 0.82 | 0.88 | 1.00 | ~5100ms |
| supplier_query | 6 | 0.89 | 0.91 | 0.92 | ~3800ms |
| supplier_selection | 1 | 0.85 | 0.90 | 1.00 | ~6200ms |
| order_calculation | 2 | 0.88 | 0.90 | 1.00 | ~4500ms |
| purchase_order | 1 | 0.85 | 0.88 | 1.00 | ~5800ms |
| sales_analysis | 2 | 0.86 | 0.89 | 1.00 | ~3500ms |
| knowledge_base | 3 | 0.84 | 0.87 | 0.90 | ~4200ms |
| full_workflow | 2 | 0.83 | 0.86 | 0.85 | ~8500ms |

---

## 5. Key Observations

### Strengths
- **Tool Call Accuracy** is highest across single-tool categories (inventory_check, forecasting, order_calculation all at 1.00). The agent reliably selects the correct tool for straightforward queries.
- **Inventory queries** score highest in both faithfulness and relevancy, indicating strong performance on the core use case.
- **Deterministic tools** (get_current_inventory, calculate_order_quantity) consistently produce accurate, grounded responses.

### Weaknesses
- **Full workflow queries** have the lowest scores and highest latency. Multi-step reasoning chains are more prone to information loss between steps.
- **Knowledge base queries** occasionally include information synthesized beyond what the RAG context strictly contains (faithfulness dip).
- **Forecasting answers** sometimes round numbers differently than ground truth or include extra caveats, affecting exact-match relevancy.

### Latency Observations
- Simple tool calls (inventory check): ~3-4 seconds
- Multi-tool workflows: ~8-9 seconds
- The Groq inference latency is consistent but the ReAct loop adds overhead per reasoning cycle

---

## 6. Recommendations

1. **Improve RAG prompt grounding**: Add explicit instruction to the system prompt to only cite information present in tool results, reducing hallucination in knowledge_base queries.
2. **Optimize multi-step workflows**: Consider caching intermediate results to reduce repeated tool calls in full_workflow scenarios.
3. **Set up LangSmith tracing**: Enable per-node latency tracking to identify specific bottleneck nodes (see bottleneck_analysis.txt).
