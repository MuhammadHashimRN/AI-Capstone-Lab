"""
Configuration for the Dynamic Inventory Reorder Agent.
All credentials are read exclusively from environment variables.
No secret may have a hardcoded fallback in this file.

Set before running:
    export GROQ_API_KEY="<your-groq-key>"
    export LANGSMITH_API_KEY="<your-langsmith-key>"   # optional
"""

import os
import sys

# ─── Groq API Configuration ─────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TEMPERATURE = 0.1

# ─── Embedding Configuration ────────────────────────────────────────────────
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ─── ChromaDB Configuration ─────────────────────────────────────────────────
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
CHROMA_COLLECTION_NAME = "inventory_knowledge_base"

# ─── Data Paths ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "Initial_Data")
SALES_HISTORY_PATH = os.path.join(DATA_DIR, "sales_history.csv")
INVENTORY_LEVELS_PATH = os.path.join(DATA_DIR, "inventory_levels.csv")
SUPPLIER_CATALOGS = [
    os.path.join(DATA_DIR, "supplier_catalog_techdist.csv"),
    os.path.join(DATA_DIR, "supplier_catalog_globalelec.csv"),
    os.path.join(DATA_DIR, "supplier_catalog_primeparts.csv"),
]
PROMOTIONAL_CALENDAR_PATH = os.path.join(DATA_DIR, "promotional_calendar.csv")

# ─── Agent Thresholds ───────────────────────────────────────────────────────
AUTO_APPROVE_THRESHOLD = 10000  # Orders below $10K are auto-approved
REORDER_LEAD_BUFFER_DAYS = 3    # Extra buffer days added to lead time
SAFETY_STOCK_MULTIPLIER = 1.5   # Safety stock = avg_daily_demand * multiplier * lead_time

# ─── Checkpointer ───────────────────────────────────────────────────────────
CHECKPOINT_DB_PATH = os.path.join(os.path.dirname(__file__), "checkpoint_db.sqlite")

# ─── LangSmith Observability ───────────────────────────────────────────────
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "inventory-reorder-agent")
LANGSMITH_TRACING = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"


def enable_langsmith() -> bool:
    """Enable LangSmith tracing when LANGSMITH_API_KEY is present in the environment.
    Returns True if tracing was activated, False otherwise."""
    if LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
        return True
    return False


def require_groq_key() -> None:
    """Exit with a clear error if GROQ_API_KEY is not set.
    Call this at the top of any script that needs the LLM."""
    if not GROQ_API_KEY:
        print(
            "[ERROR] GROQ_API_KEY environment variable is not set.\n"
            "  Local:  export GROQ_API_KEY='<your-key>'\n"
            "  Docker: add it to your .env file (see .env.example)\n"
            "  CI:     store it in GitHub Secrets as GROQ_API_KEY",
            file=sys.stderr,
        )
        sys.exit(1)
