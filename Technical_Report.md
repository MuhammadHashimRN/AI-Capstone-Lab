# Technical Report: Dynamic Inventory Reorder Agent

## 1. System Overview

The Dynamic Inventory Reorder Agent is an autonomous supply chain management system built on **LangGraph**, a framework for constructing stateful, multi-actor applications with Large Language Models (LLMs). The system addresses a critical business problem: an electronics retailer losing $2M annually to stockouts and $500K to excess inventory due to reactive, manual procurement processes.

### Architecture

The system follows a layered architecture with four primary components:

1. **Data Layer**: SQLite databases store transactional data (sales history, current inventory, supplier records, purchase orders), while ChromaDB provides a vector store for unstructured knowledge (supplier catalogs, inventory policies, market reports).

2. **Tool Layer**: Seven specialized tools expose database operations, forecasting algorithms, and business logic as callable functions that the LLM can invoke through the ReAct reasoning loop.

3. **Agent Layer**: LangGraph orchestrates the reasoning process. In single-agent mode, one ReAct agent iteratively calls tools to gather data, analyze it, and take action. In multi-agent mode, an Inventory Researcher gathers data before handing off to a Procurement Analyst for decision-making.

4. **Safety Layer**: Human-in-the-loop (HITL) interrupts pause execution before high-risk actions (purchase order generation), and SQLite-backed checkpointing enables state persistence across sessions.

### Why LangGraph Over Simple Chains

A traditional LangChain sequential chain (prompt → LLM → output) cannot solve this problem because inventory reordering requires **iterative reasoning with branching logic**. The agent must:
- Dynamically decide which tools to call based on intermediate results (e.g., only forecast demand if stock is low)
- Handle multi-step reasoning where each step depends on the previous one
- Support conditional branching (reorder vs. no-reorder paths)
- Maintain state across multiple tool invocations

LangGraph's `StateGraph` provides exactly this: a directed graph where nodes are computational steps (agent reasoning, tool execution) and edges define the flow based on runtime conditions. The `ToolNode` prebuilt component handles the mechanical execution of tool calls, while conditional edges implement the ReAct loop's "reason → act → observe" cycle. This graph-based approach is fundamentally more powerful than a linear chain because it supports cycles (the agent can call tools repeatedly until satisfied) and conditional routing (different paths for different scenarios).

---

## 2. RAG Implementation

### Chunking Strategy

The ingestion pipeline uses `RecursiveCharacterTextSplitter` with a chunk size of 800 tokens and 150-token overlap. These parameters were chosen based on the nature of the source documents:

- **800 tokens** is large enough to capture a complete supplier catalog entry (SKU, price, MOQ, lead time) or a full policy section (reorder point formula with context), but small enough to maintain retrieval precision. Larger chunks would dilute relevance scores when the query targets a specific SKU.
- **150 tokens of overlap** ensures that sentences split at chunk boundaries are not lost. This is particularly important for policy documents where a formula definition might span the boundary.

A critical design decision is the **table preservation logic**: when the ingestion pipeline detects pricing table content (multiple dollar signs or SKU identifiers in a text block), it switches to a larger chunk size of 1,500 tokens. This prevents the splitter from breaking a pricing table mid-row, which would make individual rows meaningless to the retrieval system. For example, splitting "SKU-001 | Wireless Headphones Pro | $15.00" across two chunks would make neither chunk useful for a pricing query.

### Metadata Design

Every chunk is enriched with five metadata fields:

| Field | Purpose | Example |
|-------|---------|---------|
| `doc_type` | Enables source-type filtering | `supplier_catalog` |
| `department` | Role-based access patterns | `procurement` |
| `priority_level` | Triage and ranking | `high` |
| `last_updated` | Freshness verification | `2024-01-15` |
| `source_file` | Audit trail | `supplier_catalog_techDistributors.pdf` |

The `doc_type` filter is the most impactful for retrieval quality. When the agent asks "What is the price for SKU-001?", filtering to `doc_type=supplier_catalog` eliminates noise from market reports that might mention pricing trends at different price points. Without this filter, ChromaDB might return a market report paragraph about "wireless headphone pricing trends" instead of the actual supplier price list.

### Retrieval Quality

The combination of semantic search (OpenAI's text-embedding-3-small) and metadata filtering achieves high precision for the three primary query patterns: pricing lookups, policy queries, and trend analysis. The embedding model captures domain-specific relationships (e.g., "lead time" relates to "delivery" and "shipping days") while metadata filters eliminate cross-domain contamination.

---

## 3. Multi-Agent Design

### Why Two Agents vs. One

The single-agent ReAct loop works well for straightforward queries, but it suffers from **instruction creep** in complex scenarios. When one agent is responsible for both research and decision-making, the system prompt must contain instructions for both phases, leading to:

1. **Premature action**: The agent might generate a purchase order before completing research, especially if early tool results suggest urgency.
2. **Tool confusion**: With all 7 tools available, the LLM occasionally calls procurement tools (like `generate_purchase_order`) during what should be the research phase.
3. **Prompt bloat**: Combining researcher and analyst instructions into one system prompt reduces the LLM's adherence to each individual instruction.

The two-agent design solves these problems through **tool restriction** and **explicit handover**:

- **Agent A (Inventory Researcher)** only has access to data-gathering tools (`get_current_inventory`, `get_sales_data`, `forecast_demand`, `query_supplier_catalog`). It physically cannot generate a purchase order, regardless of what the LLM decides.
- **Agent B (Procurement Analyst)** only has access to decision-making tools (`calculate_order_qty`, `generate_purchase_order`, `send_alert`). It cannot query databases, forcing it to rely entirely on Agent A's research.

### Handover Mechanism

The handover between agents is triggered by a keyword signal: when Agent A includes "RESEARCH_COMPLETE" in its output, the router function redirects flow from the Agent A loop to a handover node. This node extracts Agent A's research summary and injects it as a `HumanMessage` into Agent B's context, effectively briefing Agent B on the situation.

This design creates a clear **audit trail**: the handover point is a discrete, loggable event where we can verify that Agent A completed its research before any purchasing decision was made. In a production system, this handover could trigger additional validation (e.g., checking that Agent A queried at least 2 data sources before handover).

### Tool Restriction Benefits

Tool restriction prevents a class of errors that are difficult to detect in single-agent systems. If Agent A could generate purchase orders, a hallucinated urgency assessment could trigger an immediate, unauthorized purchase. By restricting Agent A to read-only operations, the worst-case failure mode is incomplete research — which Agent B can detect and flag — rather than an unauthorized financial commitment.

---

## 4. HITL & Safety

### High-Risk Action Identification

The `generate_purchase_order` tool is identified as the highest-risk action in the system because it represents a **financial commitment**. Unlike data-gathering tools (which are idempotent and reversible), a generated purchase order may be transmitted to a supplier and result in real financial obligations. The approval threshold policy reinforces this:
- Orders under $1,000 are auto-approved
- Orders $1,000–$5,000 require Procurement Manager approval
- Orders over $5,000 require Director approval

The HITL interrupt is implemented using LangGraph's `interrupt_before` parameter, which pauses graph execution before the `purchase_order_node` runs. This gives the human operator three options:

1. **Proceed**: Resume execution with the proposed order unchanged
2. **Cancel**: Terminate the workflow and log the cancellation
3. **Edit**: Modify the order quantity or supplier, update the graph state, and resume

The Edit option is particularly powerful because it uses LangGraph's `update_state` API to inject modified parameters into the graph state. This means the agent doesn't need to re-run its entire analysis — only the purchase order generation step is affected.

### Checkpointing and Audit Trails

The `SqliteSaver` checkpointer persists the complete graph state (all messages, tool call results, and state variables) to a SQLite database after every node execution. This serves two purposes:

1. **Session persistence**: If the agent process crashes or the user closes their terminal, the conversation can be resumed from the last checkpoint using the same `thread_id`. The persistence test demonstrates this by running two sessions with the same thread ID and verifying that Session 2 has access to Session 1's context.

2. **Audit compliance**: Every tool call, LLM response, and state transition is recorded with timestamps. For a procurement system handling real money, this audit trail is essential for post-facto review of purchasing decisions. If a purchase order is later questioned, auditors can replay the exact sequence of data gathering, analysis, and decision-making that led to it.

### State Editing Use Cases

The ability to edit graph state mid-execution (via `update_state`) enables several important scenarios:
- **Quantity adjustment**: The agent recommends 300 units, but the manager knows a promotion is ending and reduces to 150
- **Supplier override**: The agent selects the cheapest supplier, but the manager prefers a more reliable one
- **Emergency escalation**: The manager increases urgency level on an alert before it's sent
- **Budget constraints**: The manager caps the order total at a specific dollar amount

Each of these represents a case where human judgment complements algorithmic optimization — the agent provides the data-driven recommendation, and the human applies business context that the agent cannot access.
