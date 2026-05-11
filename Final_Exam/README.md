# AI407L Final Exam — Submission Index

This directory contains the deliverables for the AI407L Spring 2026 final
exam. It is organised into two self-contained sub-projects: Part A (Drift
Monitoring & Feedback Loops, layered on top of the inventory agent built
across Labs 1–11) and Part B (a standalone Self-RAG University Course
Advisory Agent built on the provided `data_share` PDFs).

```
Final_Exam/
├── Part_A/                              [40 marks]
│   ├── seed_feedback.py                 captures real /chat interactions
│   ├── feedback_log.json                12 logged interactions (Good/Bad)
│   ├── analyze.py                       totals + Top-3 failed queries
│   ├── analysis_report.md               auto-generated analysis
│   └── improvement_demo.md              issue, fix, before/after evidence
└── Part_B/                              [60 marks]
    ├── data/                            5 provided PDFs (read-only)
    ├── ingest_data.py                   PDF → ChromaDB ingestion
    ├── tools.py                         @tool + Pydantic (kb + web search)
    ├── graph.py                         Self-RAG LangGraph StateGraph
    ├── self_rag_agent.py                interactive CLI entry point
    ├── run_tests.py                     test harness (6 scenarios)
    ├── evaluation_results.md            auto-generated test traces
    ├── test_traces.json                 machine-readable per-test state
    └── chroma_db/                       generated at runtime
```

---

## Part A — Drift Monitoring & Feedback Loops

Built directly on top of the inventory agent's live `POST /chat` endpoint.
No mocked responses — every entry in `feedback_log.json` was produced by
calling the running agent.

### Required deliverables (exam rubric)

| Rubric item | File |
|---|---|
| Feedback log (JSON/CSV/SQLite with `user_input`, `agent_response`, `feedback`) | `feedback_log.json` |
| `analyze.py` (totals, negative count, Top-3 failed queries) | `analyze.py` |
| Analysis report | `analysis_report.md` |
| Improvement demo (issue → fix → before vs after) | `improvement_demo.md` |

### Run it

```bash
# 1. Make sure the inventory FastAPI is up on :8000.
# 2. Collect 12 real interactions and grade them:
python Final_Exam/Part_A/seed_feedback.py

# 3. Generate the markdown analysis report:
python Final_Exam/Part_A/analyze.py
```

Stdout for the analyze step:

```
============================================================
FEEDBACK ANALYSIS
============================================================
Total responses        : 12
Negative feedback (Bad): 2

Top 3 Failed Queries:
  1. [x1] Which supplier offers the lowest price for SKU-001?
  2. [x1] Generate a purchase order for SKU-004 from TechDistributors for 100 units at $25.
============================================================
```

The issue identified and fixed in `improvement_demo.md`: the agent was
calling `select_best_supplier` (multi-criteria weighted scoring) when the
user asked for the literal lowest price. Patching the system prompt with
explicit user-intent rules collapsed both failed queries from 2 tool
calls (wrong supplier) to 3× `query_all_suppliers` (correct GlobalElec
$14.50) and 7 tool calls (override) to 1× `generate_purchase_order`
(direct execution).

---

## Part B — Self-RAG University Course Advisory Agent

A standalone Self-RAG pipeline implemented in LangGraph. The agent answers
questions about XYZ National University using ONLY the provided 5 PDFs as
its knowledge base, with a web-search fallback when the local KB cannot
answer.

### Pipeline (StateGraph)

```
START
  │
  ▼
[route_query]                — Adaptive retrieval decision (LLM classifier)
  │
  ├── NO_RETRIEVE ───────► [direct_answer] ─► END
  │
  └── RETRIEVE
       │
       ▼
   [retrieve]                — Pulls top-8 candidates from ChromaDB
       │
       ▼
   [grade_documents]         — Per-doc YES/NO relevance check (LLM)
       │
       ├── ≥1 relevant ─► [generate] ─┐
       │                              │
       └── 0 relevant ──► [web_search] ─► [generate]
                                          │
                                          ▼
                                  [hallucination_check]
                                          │
                                          ├── grounded ──► [finalize] ─► END
                                          │
                                          ├── retry < 2 ─► back to [generate]
                                          │
                                          └── retry ≥ 2 ─► [finalize] (disclaimer)
```

### Required deliverables (exam rubric)

| Rubric item | File |
|---|---|
| `self_rag_agent.py` — interactive entry point | `self_rag_agent.py` |
| `graph.py` — StateGraph implementation | `graph.py` |
| `tools.py` — @tool + Pydantic | `tools.py` |
| `evaluation_results.md` — 5+ test cases with traces | `evaluation_results.md` |

### Tools (with @tool + Pydantic validation)

| Tool | Purpose |
|---|---|
| `query_knowledge_base(query, top_k, doc_type, department)` | ChromaDB retrieval with optional metadata filters |
| `web_search(query, num_results)` | DuckDuckGo fallback when KB returns no relevant docs |

### Knowledge base

| PDF | Chunking strategy | Chunks indexed |
|---|---|---|
| `CS_Department_Catalog.pdf` | Per-course block (regex on `<DEPT>-<NUM>:` header) | 13 |
| `EE_Department_Catalog.pdf` | Per-course block | 9 |
| `BBA_Department_Catalog.pdf` | Per-course block | 8 |
| `University_Academic_Policies.pdf` | Per numbered policy section | 12 |
| `Faculty_Directory.pdf` | Per faculty row + contact footer | 15 |
| **Total** | | **57** |

Every chunk carries 7 metadata fields: `doc_type`, `department`,
`source_file`, `course_code`, `course_level`, `section_title`,
`faculty_name`.

### Test coverage (live runs — see `evaluation_results.md`)

| # | Scenario | needs_retrieval | graded | used_web | retry | grounded |
|---|---|---|---|---|---|---|
| 1 | Greeting (NO_RETRIEVE) | **False** | 0 | False | 0 | True |
| 2 | CS-301 prereqs | True | 1 | False | 0 | True |
| 3 | Hostel info → **web fallback** | True | **0** | **True** | 0 | True |
| 4 | Textbook → **retry + disclaimer** | True | 0 | True | **2** | **False** |
| 5 | EE professor + office (creative) | True | 2 | False | 0 | True |
| 6 | Policy facts | True | 2 | False | 0 | True |

Every Self-RAG decision path required by the rubric is exercised at least
once across these six runs.

### Run it

```bash
# 1. Build the knowledge base:
python Final_Exam/Part_B/ingest_data.py

# 2a. Interactive REPL:
python Final_Exam/Part_B/self_rag_agent.py --interactive --trace

# 2b. Single query:
python Final_Exam/Part_B/self_rag_agent.py \
    --query "What are the prerequisites for CS-301?" --trace

# 2c. Run the full test harness and regenerate evaluation_results.md:
python Final_Exam/Part_B/run_tests.py
```

---

## Environment

Both parts run inside the project venv (`AI-Capstone-Lab/.venv/`) with
the dependencies declared in the project `requirements.txt`. Part B
additionally needs `pypdf` and `duckduckgo-search`, which were added to
the venv via `pip install` (see Final_Exam/Part_B/ingest_data.py and
tools.py for the imports).

Required environment variable:

```
GROQ_API_KEY="<your-groq-key>"   # never committed; injected at runtime
```
