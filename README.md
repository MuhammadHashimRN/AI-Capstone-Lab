# Dynamic Inventory Reorder Agent

AI407L Lab Mid Exam (Spring 2026) — GIKI

An autonomous inventory management agent built with **LangGraph** that monitors
stock levels, forecasts demand, selects suppliers, and generates purchase orders
for an electronics retailer.

## Architecture

- **LangGraph** ReAct agent loop with conditional routing
- **ChromaDB** vector store for RAG (supplier catalogs, policies, market reports)
- **SQLite** databases for transactional data (sales, inventory, suppliers, POs)
- **OpenAI GPT-4o-mini** as the reasoning engine
- **Multi-agent orchestration**: Inventory Researcher → Procurement Analyst
- **HITL safety**: Human approval before purchase order generation
- **Persistent memory**: SQLite-backed checkpointing across sessions

## Setup Guide

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create SQLite Databases

```bash
python setup_database.py
```

Creates `inventory.db` with tables: `sales_history`, `current_inventory`,
`suppliers`, `purchase_orders`. Populated with realistic data for SKU-001
through SKU-005.

### 4. Generate Sample Data Files

```bash
cd Initial_Data
python generate_sample_data.py
cd ..
```

Creates PDF and CSV files in `Initial_Data/`:
- `supplier_catalog_techDistributors.pdf` — 10 SKUs with pricing tiers
- `inventory_policy.pdf` — Reorder policies and safety stock formulas
- `market_report_electronics_2024.pdf` — Demand trends and seasonal factors
- `sales_history.csv` — 12 months of daily sales for 5 SKUs
- `supplier_performance.csv` — Supplier reliability scores

### 5. Build ChromaDB Vector Store

```bash
python ingest_data.py
```

Loads PDFs, cleans text, enriches metadata, chunks with
`RecursiveCharacterTextSplitter`, embeds with `text-embedding-3-small`,
and stores in ChromaDB at `./chroma_db`.

### 6. Run Single-Agent ReAct Loop

```bash
python run_agent.py
```

Runs the single-agent loop with the query:
> "Check inventory for SKU-001 and determine if we need to reorder."

### 7. Run Multi-Agent Collaboration

```bash
python run_multi_agent.py
```

Runs the two-agent pipeline (Inventory Researcher → Procurement Analyst)
for SKU-003. Saves the full trace to `collaboration_trace.log`.

### 8. Test Checkpointing / Persistence

```bash
python persistence_test.py thread-001
```

Demonstrates that agent state persists across sessions using SQLite-backed
checkpointing. Creates `checkpoint_db.sqlite`.

### 9. Test HITL Approval Workflow

```bash
python approval_logic.py
```

Runs the approval workflow that pauses before generating a purchase order,
allowing the user to Proceed, Cancel, or Edit the proposed order.

## Project Structure

```
├── setup_database.py          # Task 2: Creates and populates SQLite DB
├── Initial_Data/
│   └── generate_sample_data.py # Task 1: Generates PDF/CSV sample data
├── ingest_data.py             # Task 1: RAG ingestion pipeline
├── retrieval_test.md          # Task 1: RAG test queries documented
├── grounding_justification.txt # Task 1: Why RAG over raw LLM
├── tools.py                   # Task 2: 7 LangChain tools with schemas
├── graph.py                   # Task 2: LangGraph ReAct agent loop
├── run_agent.py               # Task 2: Single-agent test runner
├── agents_config.py           # Task 3: Agent persona definitions
├── multi_agent_graph.py       # Task 3: Multi-agent LangGraph
├── agent_personas.md          # Task 3: Agent documentation
├── run_multi_agent.py         # Task 3: Multi-agent test runner
├── persistence_test.py        # Task 4: SqliteSaver checkpointing
├── approval_logic.py          # Task 4: HITL safety interrupt
├── Technical_Report.md        # Technical report (4 sections)
├── PRD.md                     # Product Requirements Document
├── Architecture_Diagram.png   # System architecture diagram
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
└── .gitignore                 # Git ignore rules
```

## Key SKUs

| SKU | Product | Stock | Reorder Point | Status |
|-----|---------|-------|---------------|--------|
| SKU-001 | Wireless Headphones Pro | 35 | 50 | LOW |
| SKU-002 | USB-C Charging Cable 6ft | 450 | 200 | OK |
| SKU-003 | Bluetooth Speaker Mini | 28 | 40 | CRITICAL |
| SKU-004 | Laptop Stand Adjustable | 65 | 30 | OK |
| SKU-005 | Wireless Mouse Ergonomic | 42 | 60 | LOW |
