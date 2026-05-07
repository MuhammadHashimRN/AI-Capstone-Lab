# =============================================================================
# Dynamic Inventory Reorder Agent — Container Image
# =============================================================================
#
# BASE IMAGE JUSTIFICATION
# ────────────────────────
# python:3.11-slim is chosen over three alternatives:
#
#   python:3.11          (~920 MB) — full Debian; includes man pages, Perl,
#                                    and dozens of packages we never use.
#   python:3.11-alpine   (~50 MB)  — musl libc breaks hnswlib (chromadb's
#                                    HNSW index), sentence-transformers, and
#                                    several other native C extensions.
#   python:3.11-slim     (~150 MB) — Debian base stripped to runtime essentials.
#                                    Supports all native extensions once
#                                    build-essential is added. ✓ CHOSEN
#   python:3.11-bookworm (~920 MB) — same as full; unnecessary size.
#
# Python 3.11 (not 3.12/3.13) is pinned because LangGraph >=1.0 and
# sentence-transformers >=5.0 declare 3.11 in their tested matrix.
#
# LAYER ORDERING STRATEGY
# ────────────────────────
# Docker caches each layer. Re-using cached layers avoids re-running the
# slow pip install step on every code change. The order is:
#   1. System packages   — changes rarely (new OS dep)
#   2. requirements.txt  — changes occasionally (new Python dep)
#   3. Application code  — changes frequently (every commit)
#
# By copying requirements.txt BEFORE the source code, changing a .py file
# only invalidates layers 3 onward; layers 1-2 are served from cache.
#
# MULTI-STAGE BUILD DECISION
# ──────────────────────────
# A multi-stage build is not used here because:
#   • sentence-transformers downloads ~420 MB of model weights at runtime
#     (not at build time), so a slim runtime stage gains little.
#   • The build tools (build-essential) are only needed during pip install;
#     they add ~200 MB to the builder stage but would be excluded from a
#     runtime stage. This trade-off is noted but not implemented here to
#     keep the Dockerfile readable for the coursework submission.
#   • A production hardening step would add a second stage; documented in
#     the Deployment Report.
# =============================================================================

FROM python:3.11-slim

# ── 1. System packages ───────────────────────────────────────────────────────
# build-essential: C compiler and headers — required by chromadb's hnswlib and
#                  tokenizers wheels which ship no pre-built binary for slim.
# curl:            used by Docker's HEALTHCHECK to probe GET /health.
# Combine update + install + clean in ONE RUN to avoid a dangling apt layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── 2. Working directory ─────────────────────────────────────────────────────
WORKDIR /app

# ── 3. Python dependencies (cached until requirements.txt changes) ───────────
# Copy ONLY the requirements file first.
# This layer is rebuilt only when requirements.txt is modified —
# not on every source-code change.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── 4. Application source code ───────────────────────────────────────────────
# Copied after dependencies so that editing .py files does not invalidate
# the expensive pip layer above.
COPY . .

# ── 5. Volume mount-point directories ───────────────────────────────────────
# Pre-create directories so named volumes attach cleanly on first start.
# Data inside these paths is supplied at runtime via docker-compose volumes —
# nothing sensitive is baked into the image.
RUN mkdir -p /app/chroma_db /app/purchase_orders /app/Initial_Data

# ── SECRET POLICY ────────────────────────────────────────────────────────────
# GROQ_API_KEY and LANGSMITH_API_KEY are intentionally absent from this file.
# They are injected at container start time via:
#   docker compose  → environment: / env_file: .env
#   docker run      → -e GROQ_API_KEY=...
# config.py reads them with os.environ.get() and has no hardcoded fallback.
# The .dockerignore file excludes .env, *.env, venv/, __pycache__/, and
# all local SQLite databases from the build context.

EXPOSE 8000

# ── Health check ─────────────────────────────────────────────────────────────
# start-period=60s: sentence-transformers downloads the embedding model on
# first start. The container is not marked healthy until /health returns 200.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Entrypoint ───────────────────────────────────────────────────────────────
# workers=1: LangGraph's SqliteSaver checkpointer opens the SQLite file with
# check_same_thread=False but is not safe across OS-level processes.
# Horizontal scaling should use multiple container replicas, not multiple
# workers within one container.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
