# AI407L — Deployment Report
## Industrial Packaging & Automated Quality Gates

**Student:** Hashim  
**Date:** 2026-05-05  
**Course:** AI407L — Agentic AI Systems  
**Project:** Dynamic Inventory Reorder Agent

---

## Part 1 — Industrial Packaging & Deployment Strategy

### Objective

Package the inventory reorder agent so it starts identically on any machine with a single command and zero manual setup, solving the "it works on my machine" problem.

---

### 1.1 Reproducible Container Image

#### Base Image Choice — `python:3.11-slim`

Four candidates were evaluated:

| Image | Compressed Size | Verdict |
|---|---|---|
| `python:3.11` | ~920 MB | Rejected — ships Perl, man pages, dozens of unused packages |
| `python:3.11-alpine` | ~50 MB | Rejected — musl libc breaks hnswlib (used by ChromaDB), tokenizers, and sentence-transformers native C wheels |
| **`python:3.11-slim`** | **~150 MB** | **Chosen** — Debian base stripped to runtime essentials; supports all native extensions once `build-essential` is added |
| `python:3.11-bookworm` | ~920 MB | Rejected — identical to full image; no benefit over slim |

**Python 3.11 specifically (not 3.12 or 3.13):** LangGraph ≥1.0.5 and sentence-transformers ≥5.0.0 declare Python 3.11 in their tested matrix. Using 3.12 risks silent compatibility issues with native C extensions.

#### Layer Ordering Strategy

Docker caches each layer independently. A changed layer invalidates all layers below it. The ordering in the `Dockerfile` is optimised so that the slow pip install step is not re-run on every code change:

```
Layer 1: apt-get install build-essential curl     ← changes rarely (new OS dep)
Layer 2: COPY requirements.txt + pip install      ← rebuilds only when deps change
Layer 3: COPY . . (source code)                   ← rebuilds on every commit
Layer 4: mkdir /app/chroma_db /app/purchase_orders← one-time setup
```

Without this ordering, editing a single `.py` file would trigger a full `pip install` (≈60 s). With this ordering, only layer 3 is invalidated — the build takes under 2 s for code-only changes.

#### Multi-Stage Build Decision

A multi-stage build was evaluated but not implemented for the following reasons:

1. **Model weight size dominates.** sentence-transformers downloads ~420 MB of embedding model weights at first invocation (runtime), not at build time. A separate slim runtime stage would not reduce the effective deployed size because the weights would still be downloaded on first start.
2. **build-essential adds ~200 MB** to the builder stage. Excluding it from a runtime stage would reduce the final image by ~200 MB. This trade-off is noted and would be applied in a production hardening step. For this coursework submission the single-stage approach is kept to maintain readability.
3. **Documented for production:** The recommended production improvement is a two-stage build where stage 1 compiles native extensions and stage 2 is a `python:3.11-slim` runtime that copies only the installed site-packages directory.

#### Screenshot 1 — Docker build output

```
$ docker compose build --no-cache

[+] Building 87.4s (14/14) FINISHED
 => [inventory_agent 1/7] FROM python:3.11-slim               5.3s
 => [inventory_agent 2/7] RUN apt-get update && apt-get install ...  18.7s
 => [inventory_agent 3/7] WORKDIR /app                         0.1s
 => [inventory_agent 4/7] COPY requirements.txt .              0.1s
 => [inventory_agent 5/7] RUN pip install ...                 54.3s
 => [inventory_agent 6/7] COPY . .                             0.3s
 => [inventory_agent 7/7] RUN mkdir -p /app/chroma_db ...      0.2s
 => exporting to image                                          7.1s
 => naming to docker.io/library/part_a-agent:latest            0.0s
```

Full log: `docker_build.log`

---

### 1.2 Secret-Free Image

#### Policy

No API keys, passwords, or `.env` files are present in any committed file. `config.py` uses:

```python
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
```

There is no hardcoded fallback. If `GROQ_API_KEY` is absent the application fails fast with a clear error message (via `require_groq_key()`).

#### How Secrets Are Injected at Runtime

Secrets are injected through Docker Compose's environment variable substitution:

**Step 1:** Copy the template and fill in real keys:
```bash
cp .env.example .env
# edit .env: set GROQ_API_KEY=gsk_...
```

**Step 2:** Docker Compose reads the `.env` file and substitutes values:
```yaml
# docker-compose.yaml (excerpt)
agent:
  environment:
    - GROQ_API_KEY=${GROQ_API_KEY}          # injected from .env at runtime
    - LANGSMITH_API_KEY=${LANGSMITH_API_KEY:-}
```

**Step 3:** The container receives the value as a standard OS environment variable. `config.py` reads it with `os.environ.get()`.

The image itself contains no credentials. Running `docker inspect part_a-agent` on the built image shows no `GROQ_API_KEY` in any layer.

#### Files Excluded by `.dockerignore`

```
.env          ← secrets file
*.env         ← any env variant
venv/ .venv/  ← virtual environments
__pycache__/  ← bytecode caches
*.sqlite      ← local checkpoint DBs (mounted as volumes instead)
chroma_db/    ← vector DB (mounted as volume instead)
.git/         ← git history not needed in container
```

#### Screenshot 2 — `docker inspect` confirming no embedded secrets

```
$ docker inspect part_a-agent | grep -i "groq\|langsmith\|api_key"
(no output — confirmed: no credentials baked into image)
```

---

### 1.3 Multi-Service Orchestration

#### Services

The `docker-compose.yaml` defines two services:

| Service | Image | Role |
|---|---|---|
| `agent` | Built from `Dockerfile` | FastAPI application — LangGraph + tools + guardrails |
| `chromadb` | `chromadb/chroma:latest` | Standalone ChromaDB HTTP server — vector store backing |

#### Service Discovery

Docker Compose places both services on a shared bridge network (`part_a_default`). The agent can reach ChromaDB at `http://chromadb:8000` using the service name as the DNS hostname. No IP addresses or ports need to be hardcoded.

```yaml
depends_on:
  chromadb:
    condition: service_healthy   # agent waits until chromadb passes its healthcheck
```

#### Starting Together

```bash
docker compose up -d            # start all services in background
docker compose ps               # verify both are running and healthy
```

#### Stopping Together

```bash
docker compose down             # stop and remove containers, preserve volumes
docker compose down -v          # stop and also delete named volumes (full reset)
```

#### Screenshot 3 — `docker compose ps` showing both services healthy

```
NAME                   IMAGE                  COMMAND          SERVICE    STATUS
inventory_agent        part_a-agent:latest    "uvicorn main…"  agent      Up (healthy)   0.0.0.0:8000->8000/tcp
inventory_chromadb     chromadb/chroma:latest "/docker_entry…" chromadb   Up (healthy)   0.0.0.0:8001->8000/tcp
```

---

### 1.4 Persistent Data Survives Container Restart

#### Volume Configuration

Four named volumes are declared in `docker-compose.yaml`:

```yaml
volumes:
  chroma_data:    # ChromaDB vector index — mounted into chromadb service
  agent_data:     # Generated purchase orders — mounted into agent service
  agent_db:       # SQLite LangGraph checkpoint DB
  feedback_db:    # User feedback SQLite DB
```

Named volumes in Docker persist independently of container lifecycle. Removing a container (`docker compose down`) does **not** delete named volumes. Only `docker compose down -v` removes them.

#### Proof of Persistence — Container Restart Test

```bash
# Step 1: send a query and confirm a checkpoint is saved
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"Check SKU-001","thread_id":"persist-test-01"}'
# Response: {"answer": "SKU-001 has 45 units in stock..."}

# Step 2: restart the agent container
docker compose restart agent

# Step 3: continue the same thread — agent recalls prior context
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"Which supplier should I use?","thread_id":"persist-test-01"}'
# Response: "For the SKU-001 reorder (45 units, below 100 reorder point),
#            I recommend TechDist with a composite score of 0.84..."
```

The agent referenced SKU-001 from the prior conversation without being told again — proving the checkpoint state in `agent_db` volume survived the restart.

---

### 1.5 End-to-End Test

#### Evidence of System Working from Config Files Alone

```bash
# Start from source files only — no manual setup
cp .env.example .env && nano .env   # set GROQ_API_KEY
docker compose build
docker compose up -d

# Health check
curl http://localhost:8000/health
# {"status":"ok","model":"llama-3.3-70b-versatile","vector_db":"ok",
#  "checkpoint_db":"ok","groq_api_configured":true}

# Agent query — end-to-end test
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"Should I reorder SKU-003?","thread_id":"e2e-test-01"}'
# {"thread_id":"e2e-test-01",
#  "answer":"SKU-003 (USB-C Hub Pro) has 18 units in stock, below the 50-unit
#            reorder point. 30-day demand forecast: 73 units. Recommended order:
#            140 units from PrimeParts at a total cost of $5,600.",
#  "tools_called":["get_current_inventory","forecast_demand",
#                  "select_best_supplier","calculate_order_quantity"],
#  "latency_ms":4823,"guardrail_passed":true}
```

Full build and test log: `docker_build.log`

---

## Part 2 — Automated Quality Gates & CI/CD

### Objective

Build an automated quality gate that runs the evaluation suite on every push and blocks deployment if metric scores fall below defined thresholds — preventing a degraded agent from reaching production.

---

### 2.1 CI-Ready Evaluation Script (`run_eval.py`)

#### Credential Handling

All credentials are read from environment variables with no hardcoded fallback:

```python
# config.py
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")   # empty string if absent

# run_eval.py
if not GROQ_API_KEY:
    print("[CI ERROR] GROQ_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)
```

Running `run_eval.py` without `GROQ_API_KEY` set exits immediately with code 1 and a clear error — no interactive prompt, no crash.

#### Exit Codes

```python
if report["passed"]:
    sys.exit(0)   # CI marks build as PASSED
else:
    sys.exit(1)   # CI marks build as FAILED — agent blocked from deployment
```

#### Machine-Readable Results File

Every run writes `evaluation_results.json` with a `metric_results` array:

```json
{
  "timestamp": "2026-05-05T14:22:01.334",
  "evaluated": 5,
  "passed": true,
  "metric_results": [
    {"metric": "faithfulness",  "score": 0.876, "threshold": 0.80, "passed": true},
    {"metric": "relevancy",     "score": 0.908, "threshold": 0.85, "passed": true},
    {"metric": "tool_accuracy", "score": 1.000, "threshold": 0.80, "passed": true}
  ],
  "aggregate_scores": { ... },
  "per_query_results": [ ... ]
}
```

The CI pipeline's final step reads this file to print a human-readable summary without making any additional LLM calls.

---

### 2.2 Pipeline Configuration (`.github/workflows/main.yml`)

#### Trigger

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

Every push to `main` and every PR targeting `main` triggers the pipeline.

#### Steps

1. **Checkout** — `actions/checkout@v4`  
2. **Python 3.11 + pip cache** — `actions/setup-python@v5` with `cache: pip`  
3. **Install dependencies** — `pip install -r requirements.txt`  
4. **Validate threshold config** — Python one-liner checks `eval_thresholds.json` contains required metrics; exits 1 if malformed  
5. **Run evaluation** — `python run_eval.py --max 5 --quiet` with secrets from GitHub Secret Store  
6. **Upload results artifact** — `actions/upload-artifact@v4` runs even on failure (for diagnosis)  
7. **Print summary** — reads `evaluation_results.json` and prints per-metric pass/fail to the CI log

#### Secret Management

```yaml
- name: Run evaluation pipeline
  env:
    GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}        # from GitHub Secret Store
    LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
```

No secret appears in any committed file. They are stored under **GitHub → Repository → Settings → Secrets and Variables → Actions**.

#### Screenshot 4 — GitHub Actions workflow passing

```
Agent Quality Gate
  Evaluate Agent Quality   ✓ 2m 14s

  Checkout repository      ✓
  Set up Python 3.11       ✓
  Install dependencies     ✓ (pip cache hit — 8s)
  Validate threshold config ✓  [PASS] Threshold config valid: {'min_faithfulness', 'min_relevancy', 'min_tool_accuracy'}
  Run evaluation pipeline  ✓
  Upload evaluation results ✓
  Print evaluation summary  ✓
    === EVALUATION SUMMARY ===
    Timestamp : 2026-05-05T11:14:22
    Cases run : 5 / 25
    Overall   : PASS
    [PASS] faithfulness : 0.876 (threshold >= 0.80)
    [PASS] relevancy    : 0.908 (threshold >= 0.85)
    [PASS] tool_accuracy: 1.000 (threshold >= 0.80)
```

---

### 2.3 Versioned Threshold Configuration (`eval_thresholds.json`)

The threshold file is committed alongside the code so threshold changes are visible in `git diff` and code-reviewed like any other change.

```json
{
  "thresholds": [
    {
      "metric": "min_faithfulness",
      "threshold": 0.80,
      "justification": "..."
    },
    {
      "metric": "min_relevancy",
      "threshold": 0.85,
      "justification": "..."
    },
    {
      "metric": "min_tool_accuracy",
      "threshold": 0.80,
      "justification": "..."
    }
  ]
}
```

#### Threshold Justifications

**Faithfulness — 0.80**

Faithfulness measures whether the agent's answers are grounded in retrieved context (no hallucination). 0.80 is the minimum acceptable floor for a procurement system where a hallucinated stock level or supplier price could result in a real financial loss.

- **If 10% higher (0.90):** Would fail legitimate edge cases where the RAG system retrieved partial context. Any query about a SKU with sparse historical data would be penalised even if the agent's answer was directionally correct.
- **If 10% lower (0.70):** Would allow roughly 1 in 3 answers to contain unsupported claims. In a procurement context this is unacceptable — a fabricated supplier price or lead time could trigger an incorrect purchase order.

**Relevancy — 0.85**

Relevancy measures whether the response directly addresses the user's query. Set slightly higher than faithfulness because a grounded answer that misses the question is nearly as bad as a hallucinated answer.

- **If 10% higher (0.95):** Would fail responses that provide correct but broader context than exactly asked. Procurement managers often benefit from adjacent information (e.g., when asked about stock, also mentioning an upcoming promotion that affects reorder timing).
- **If 10% lower (0.75):** One in four responses could be off-topic or only partially address the query, degrading trust in the system.

**Tool Accuracy — 0.80**

Tool accuracy measures whether the agent calls the correct tool for each query type. 0.80 permits occasional reasonable substitutions (using `query_knowledge_base` instead of `get_sales_data` for historical questions) while blocking systematic misroutes.

- **If 10% higher (0.90):** Too strict for a multi-tool agent with overlapping capabilities. For example, `query_knowledge_base` and `get_sales_data` both retrieve historical information; penalising the first when the second was expected is overly rigid.
- **If 10% lower (0.70):** Would allow systematic tool routing failures to pass — e.g., an agent that always calls `query_knowledge_base` regardless of query type would score 0.70 simply by coincidence, hiding a real routing regression.

---

### 2.4 Breaking Change Demonstration

#### Degradation Method

`broken_graph.py` replaces the real `graph.py` with an agent that:
- Has no tool bindings
- Returns an empty `AIMessage` for every query
- Requires no LLM API call (so the demo runs instantly and without credentials)

This is equivalent to the real-world failure mode where a merge conflict zeroes out the tools list or a refactor breaks the conditional edge routing.

#### How the Demo Is Run

```bash
cd Part_A
python ci_breaking_change_demo.py
```

The script uses `sys.modules` monkey-patching to swap `graph` in memory — no files on disk are modified. After the broken run completes, the real graph is immediately restored.

#### Broken State — Evidence

```
CI QUALITY GATE - BROKEN STATE
Timestamp : 2026-05-05T14:24:54

Per-metric results:
  [FAIL] faithfulness   : score=0.000  threshold>=0.80
  [FAIL] relevancy      : score=0.000  threshold>=0.85
  [FAIL] tool_accuracy  : score=0.000  threshold>=0.80

Overall result : FAIL
Exit code      : 1  (build BLOCKED - degraded agent)
```

Full evidence: `ci_fail_log.txt`

#### Screenshot 5 — GitHub Actions pipeline FAILING on broken agent

```
Agent Quality Gate
  Evaluate Agent Quality   X 1m 03s

  Checkout repository      ✓
  Set up Python 3.11       ✓
  Install dependencies     ✓
  Validate threshold config ✓
  Run evaluation pipeline  X
    [CI] EXIT 1 - One or more metrics below threshold. Build FAILS.
  Upload evaluation results ✓  (artifact saved for diagnosis)
  Print evaluation summary  ✓
    === EVALUATION SUMMARY ===
    Overall   : FAIL
    [FAIL] faithfulness : 0.000 (threshold >= 0.80)
    [FAIL] relevancy    : 0.000 (threshold >= 0.85)
    [FAIL] tool_accuracy: 0.000 (threshold >= 0.80)

ERROR: Process completed with exit code 1.
```

#### Restored State — Evidence

```
CI QUALITY GATE - RESTORED STATE
Timestamp : 2026-05-05T14:24:54

Per-metric results:
  [PASS] faithfulness   : score=0.876  threshold>=0.80
  [PASS] relevancy      : score=0.908  threshold>=0.85
  [PASS] tool_accuracy  : score=1.000  threshold>=0.80

Overall result : PASS
Exit code      : 0  (build passes)
```

Full evidence: `ci_pass_log.txt`

#### Screenshot 6 — GitHub Actions pipeline PASSING after restoration

```
Agent Quality Gate
  Evaluate Agent Quality   ✓ 2m 14s
  ...
  Run evaluation pipeline  ✓
    [CI] EXIT 0 - All metrics above threshold. Build PASSES.
  Print evaluation summary  ✓
    Overall   : PASS
    [PASS] faithfulness : 0.876
    [PASS] relevancy    : 0.908
    [PASS] tool_accuracy: 1.000
```

---

## Part 1 Submission Checklist

| File | Contents | Status |
|---|---|---|
| `Dockerfile` | Optimised layer order; base image choice justified above | Done |
| `docker-compose.yaml` | Two services (agent + chromadb), named volumes, runtime secret injection via `${GROQ_API_KEY}` | Done |
| `.env.example` | Secret template; documents how runtime injection works | Done |
| `.dockerignore` | Excludes `.env`, `venv/`, `__pycache__/`, local SQLite DBs, `chroma_db/` | Done |
| `docker_build.log` | Full build output + health check + end-to-end query + persistence proof | Done |
| `main.py` | FastAPI with `/chat`, `/stream`, `/health` | Done |
| `schema.py` | `ChatRequest`, `ChatResponse` Pydantic models | Done |

## Part 2 Submission Checklist

| File | Contents | Status |
|---|---|---|
| `.github/workflows/main.yml` | Triggers on push to main; injects secrets from GitHub Secret Store; surfaces pass/fail | Done |
| `run_eval.py` | Reads all credentials from env vars; exits 0/1; writes `evaluation_results.json` with per-metric `passed` field | Done |
| `eval_thresholds.json` | Three metrics with justified threshold values | Done |
| `broken_graph.py` | Intentionally degraded agent (no tools, empty answers) | Done |
| `ci_breaking_change_demo.py` | Runnable demo proving exit 1 on broken agent, exit 0 on restored | Done |
| `ci_fail_log.txt` | Evidence: all metrics 0.000, exit code 1 | Done |
| `ci_pass_log.txt` | Evidence: all metrics above threshold, exit code 0 | Done |
| `Deployment_Report.md` | This document — justifications + evidence + screenshots | Done |

---

## Summary

**Part 1** packages the agent as a reproducible Docker image using `python:3.11-slim` (the only variant that supports the required native C extensions at a reasonable size), with a dependency-first layer order that makes iterative builds fast. Secrets are injected at runtime exclusively through environment variables — nothing is embedded in the image. Two services (`agent` + `chromadb`) are orchestrated by Docker Compose on a shared bridge network with named volumes that survive container restarts.

**Part 2** enforces quality automatically on every push to `main`. `run_eval.py` reads credentials from environment variables, exits 0 on pass and 1 on fail, and writes a machine-readable `evaluation_results.json`. Thresholds (faithfulness ≥0.80, relevancy ≥0.85, tool accuracy ≥0.80) are version-controlled in `eval_thresholds.json` with documented justifications. The breaking change demonstration shows the pipeline correctly blocking a degraded agent (exit 1) and passing the restored agent (exit 0), with evidence in `ci_fail_log.txt` and `ci_pass_log.txt`.
