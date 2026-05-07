# Technical Report
## Dynamic Inventory Reorder Agent — AI407L Mid-Exam

**Course**: AI407L — AI Capstone Project Lab
**Program**: BSAI, GIKI
**Date**: March 2026

---

## 1. Executive Summary

This report documents the design, implementation, and testing of a Dynamic Inventory Reorder Agent — an autonomous AI system that manages procurement for an electronics retailer. The system uses LangGraph for multi-agent orchestration, ChromaDB for RAG-based knowledge retrieval, and Groq (Llama 3.3-70B) for LLM reasoning.

The project is divided into two independent parts:
- **Part A**: A full agentic pipeline with RAG, ReAct reasoning, multi-agent collaboration, persistent memory, and human-in-the-loop safety.
- **Part B**: A standalone Model Context Protocol (MCP) pipeline demonstrating tool exposure, client-server communication, and protocol-based tool invocation.

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
User Request
     │
     ▼
┌─────────────────────────────────────────────────┐
│           LangGraph Orchestration Layer          │
│                                                   │
│  ┌──────────────────┐   ┌──────────────────────┐ │
│  │ Procurement       │──▶│ Order Manager        │ │
│  │ Analyst Agent     │   │ Agent                │ │
│  │ (Analysis Tools)  │   │ (PO Generation)      │ │
│  └────────┬─────────┘   └──────────┬───────────┘ │
│           │                        │              │
│  ┌────────▼────────────────────────▼───────────┐ │
│  │         Tool Execution Layer                 │ │
│  │  get_sales_data │ forecast_demand           │ │
│  │  get_current_inventory │ query_all_suppliers│ │
│  │  select_best_supplier │ calculate_order_qty │ │
│  │  generate_purchase_order │ query_kb         │ │
│  └────────┬────────────────────────────────────┘ │
│           │                                       │
│  ┌────────▼────────────────────────────────────┐ │
│  │    Persistent State (SqliteSaver)           │ │
│  │    + HITL Interrupt Logic                   │ │
│  └─────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│              Data & Knowledge Layer              │
│                                                   │
│  ChromaDB Vector Store │ Sales CSV │ Inventory   │
│  Supplier Catalogs     │ Promotional Calendar    │
└─────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| LLM | Groq (Llama 3.3-70B-Versatile) | Reasoning and decision-making |
| Orchestration | LangGraph 1.0.5 | State machine, multi-agent, HITL |
| RAG Vector Store | ChromaDB 1.5.1 | Semantic search with metadata filtering |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 | Text vectorization |
| Tool Framework | LangChain Core (@tool + Pydantic) | Tool definition and validation |
| Checkpointing | SqliteSaver | Persistent state management |
| MCP (Part B) | mcp 1.26.0 (FastMCP) | Model Context Protocol server/client |

---

## 3. Part A: Agent System Implementation

### 3.1 Task 1 — RAG Pipeline (Lab 2)

**File**: `ingest_data.py`

**Approach**:
- Ingests 4 data sources: supplier catalogs (3 CSV files), sales history, inventory levels, and promotional calendar.
- Each record is converted into a natural-language semantic chunk (e.g., "Supplier: TechDistributors Inc. Product: Wireless Headphones X1. Unit price: $15.00...").
- Every chunk is enriched with at least 3 metadata tags: `doc_type`, `sku`, `source_file`, plus domain-specific fields like `supplier_name`, `category`, `unit_price`.
- Text cleaning: strips HTML tags, collapses whitespace, removes noise.
- Uses SentenceTransformer (all-MiniLM-L6-v2) for embedding generation.
- ChromaDB PersistentClient stores vectors with metadata for filtered retrieval.

**Retrieval Capabilities**:
1. Semantic search across all document types.
2. Metadata-filtered queries (e.g., only supplier catalogs, only sales history).
3. Combined semantic + metadata for precise domain retrieval.

### 3.2 Task 2 — LangGraph ReAct Agent (Lab 3)

**Files**: `tools.py`, `graph.py`

**Tools Implemented** (8 total, all with @tool decorator and Pydantic input schemas):

| Tool | Input Schema | Purpose |
|------|-------------|---------|
| `get_sales_data` | SalesDataInput | Historical demand retrieval |
| `get_current_inventory` | InventoryInput | Real-time stock check |
| `forecast_demand` | ForecastInput | 30-day demand prediction |
| `query_all_suppliers` | SupplierQueryInput | Supplier comparison |
| `select_best_supplier` | SupplierSelectionInput | Multi-criteria ranking |
| `calculate_order_quantity` | OrderQuantityInput | EOQ optimization |
| `generate_purchase_order` | PurchaseOrderInput | PO document creation |
| `query_knowledge_base` | KnowledgeBaseQueryInput | RAG vector search |

**Graph Structure**:
- **State**: `AgentState` with `messages` list (annotated with `add_messages`).
- **Agent Node**: Calls Groq LLM with bound tools, returns reasoning + tool calls.
- **Tool Node**: LangGraph `ToolNode` that executes requested tools.
- **Conditional Router**: `should_continue()` checks if the last AIMessage has tool_calls → routes to "tools" node, otherwise → END.
- **Flow**: `agent → (tool calls?) → tools → agent → ... → END`

### 3.3 Task 3 — Multi-Agent Architecture (Lab 4)

**Files**: `agents_config.py`, `multi_agent_graph.py`

**Agent Personas**:
1. **Procurement Analyst**: Data gathering specialist with access to analysis tools (sales, inventory, forecasting, supplier evaluation). Cannot generate POs.
2. **Order Manager**: Execution specialist with access to PO generation. Cannot perform analysis.

**Handover Mechanism**:
- Procurement Analyst processes the request through the full analysis pipeline.
- When analysis is complete, the Analyst signals "ANALYSIS COMPLETE" in its response.
- The graph router detects this signal and transfers state to the Order Manager.
- Order Manager extracts recommendations and generates the purchase order.

**Tool Restriction**: Each agent has a restricted tool set enforced by binding only permitted tools to their LLM instance.

### 3.4 Task 4 — Persistence & HITL (Lab 5)

**Files**: `approval_logic.py`, `persistence_test.py`

**Persistent Memory**:
- Uses `SqliteSaver` checkpointer connected to `checkpoint_db.sqlite`.
- Thread IDs enable session recovery: the agent can resume from any previous conversation state.
- Verified by running a conversation, simulating a script restart, and resuming with the same `thread_id`.

**Human-in-the-Loop**:
- `generate_purchase_order` is identified as the high-risk action tool.
- The graph is compiled with `interrupt_before=["risky_tools"]` to pause execution before PO generation.
- When interrupted:
  1. The proposed action and parameters are displayed to the human.
  2. The human can APPROVE, CANCEL, or EDIT the proposed action.
  3. State editing demonstrated: human modifies the order quantity before approval.
  4. Execution resumes with the edited parameters.

---

## 4. Part B: MCP Pipeline Implementation

### 4.1 Task 1 — MCP Server (`mcp_server.py`)

**Use Case**: Weather, Currency, and Distance service for Pakistani cities.

**Tools Exposed**:
1. `get_weather_forecast(city, days)` — Returns multi-day weather forecasts.
2. `convert_currency(amount, from_currency, to_currency)` — Currency conversion with 11 supported currencies.
3. `calculate_distance(city1, city2)` — Haversine distance between Pakistani cities.

**MCP Principles**:
- Tools are defined using `@mcp.tool()` decorator on the `FastMCP` server.
- Each tool has structured input parameters with type annotations.
- Outputs are structured JSON with clear schemas.
- Server runs on stdio transport, exposing tools via MCP protocol.

### 4.2 Task 2 — MCP Client (`mcp_client.py`)

**Pipeline**:
1. **Connection**: Establishes stdio connection to MCP server using `StdioServerParameters`.
2. **Discovery**: Calls `session.list_tools()` to discover available tools at runtime.
3. **Context Exchange**: Tool schemas are formatted and passed to the Groq LLM as system context.
4. **Tool Invocation**: LLM decides which tool to call; client invokes via `session.call_tool()`.
5. **Response Handling**: Structured JSON responses are parsed and displayed.

### 4.3 Task 3 — Technical Comparison (`mcp_comparison.md`)

A structured comparison of Direct Tool Invocation, LangGraph Orchestration, and MCP Protocol across security, scalability, abstraction, and separation of concerns.

---

## 5. Algorithms and Models

### 5.1 Demand Forecasting

**Method**: Weighted Moving Average with Seasonal Adjustment
- Recent data points receive higher weights (linear weighting).
- Promotional uplift factor applied based on historical promotion frequency.
- Upcoming promotions from the calendar trigger demand multipliers.
- Confidence intervals calculated using standard deviation.

### 5.2 Supplier Selection

**Method**: Multi-Criteria Weighted Scoring
- **Price**: 40% weight (normalized, lower is better)
- **Lead Time**: 25% weight (normalized, shorter is better)
- **Reliability**: 20% weight (on-time delivery percentage)
- **Quality**: 15% weight (inverse of defect rate)
- Volume discounts are applied before scoring when order quantity exceeds threshold.

### 5.3 Order Quantity Optimization

**Method**: Economic Order Quantity (EOQ)
- Formula: EOQ = sqrt(2 * D * S / H) where D = annual demand, S = ordering cost, H = holding cost.
- Adjusted for safety stock, current inventory, and warehouse capacity constraints.

---

## 6. Testing Results

### 6.1 RAG Pipeline
- Successfully indexed 15 supplier catalog chunks, 30+ sales history summaries, 5 inventory records, and 6 promotional events.
- Metadata filtering correctly restricts results to specified document types.
- Semantic relevance ranking returns appropriate results for natural language queries.

### 6.2 ReAct Agent
- Agent correctly follows the multi-step workflow: inventory check → sales analysis → demand forecast → supplier selection → order quantity → PO generation.
- Conditional routing correctly loops between agent and tool nodes until a final answer is produced.

### 6.3 Multi-Agent System
- Procurement Analyst completes analysis and signals handover.
- Order Manager receives context and generates PO with correct parameters.
- Tool restriction enforced: Analyst cannot generate POs, Manager cannot access analysis tools.

### 6.4 Persistence & HITL
- Session recovery verified: agent resumes conversation from checkpoint after simulated restart.
- Safety interrupt triggers correctly before `generate_purchase_order`.
- State editing demonstrated: human modifies order quantity, agent executes with edited values.

---

## 7. Project Structure

```
Hashim_Capstone/
├── Part_A/
│   ├── Initial_Data/
│   │   ├── sales_history.csv
│   │   ├── inventory_levels.csv
│   │   ├── supplier_catalog_techdist.csv
│   │   ├── supplier_catalog_globalelec.csv
│   │   ├── supplier_catalog_primeparts.csv
│   │   └── promotional_calendar.csv
│   ├── config.py                  # Configuration constants
│   ├── ingest_data.py             # Lab 2: RAG pipeline
│   ├── tools.py                   # Lab 3: Tool engineering
│   ├── graph.py                   # Lab 3: LangGraph ReAct agent
│   ├── agents_config.py           # Lab 4: Agent persona definitions
│   ├── multi_agent_graph.py       # Lab 4: Multi-agent orchestration
│   ├── approval_logic.py          # Lab 5: HITL with persistence
│   ├── persistence_test.py        # Lab 5: Session recovery test
│   ├── retrieval_test.md          # Lab 2: Retrieval test documentation
│   ├── grounding_justification.txt # Lab 2: Why RAG is needed
│   └── agent_personas.md          # Lab 4: Agent role descriptions
├── Part_B/
│   ├── mcp_server.py              # MCP server with 3 tools
│   ├── mcp_client.py              # MCP client pipeline
│   └── mcp_comparison.md          # Technical comparison document
├── Technical_Report.md            # This report
├── requirements.txt               # Python dependencies
├── PRD.md                         # Product Requirements Document
└── Architecture_Diagram.png       # System architecture visual
```

---

## 8. How to Run

### Prerequisites
```bash
pip install -r requirements.txt
export GROQ_API_KEY="your-groq-api-key"
```

### Part A — Step-by-Step Execution

```bash
cd Part_A

# Step 1: Build RAG knowledge base
python ingest_data.py

# Step 2: Run ReAct agent (single agent)
python graph.py

# Step 3: Run multi-agent system
python multi_agent_graph.py

# Step 4: Run persistence test
python persistence_test.py

# Step 5: Run HITL demo
python approval_logic.py
```

### Part B — MCP Pipeline

```bash
cd Part_B

# Run MCP client (automatically starts server)
python mcp_client.py
```

---

## 9. Conclusion

This project demonstrates a complete agentic AI pipeline covering all Lab 2-5 requirements:
- **RAG grounding** ensures decisions are based on real data, not hallucinations.
- **ReAct reasoning** enables autonomous multi-step decision-making.
- **Multi-agent architecture** separates analysis from execution for higher accuracy.
- **Persistent memory** enables session recovery and continuity.
- **Human-in-the-loop** ensures safety for high-risk procurement actions.
- **MCP pipeline** demonstrates modern protocol-based tool exposure for production systems.

The system is fully functional, modular, and designed for clarity over unnecessary complexity.
