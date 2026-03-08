"""
persistence_test.py — Tests LangGraph checkpointing with SqliteSaver.

Demonstrates that agent state persists across sessions using SQLite-backed
checkpointing. Accepts a thread_id as a CLI argument.
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CHECKPOINT_DB = Path(__file__).parent / "checkpoint_db.sqlite"


def main() -> None:
    """Test state persistence across two sessions using the same thread_id."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    from graph import AgentState, build_graph

    # Accept thread_id from CLI or use default
    thread_id = sys.argv[1] if len(sys.argv) > 1 else "thread-001"
    print(f"Using thread_id: {thread_id}\n")

    # Initialize SqliteSaver
    memory = SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
    app = build_graph(checkpointer=memory)
    config = {"configurable": {"thread_id": thread_id}}

    # ── SESSION 1: Initial query ──────────────────────────────────
    print("=" * 70)
    print("SESSION 1: Initial inventory check")
    print("=" * 70)

    session1_query = "Check inventory levels for SKU-001. What is the current stock?"

    try:
        result1 = app.invoke(
            {
                "messages": [HumanMessage(content=session1_query)],
                "current_sku": "SKU-001",
                "reorder_decision": "",
            },
            config=config,
        )

        print(f"\nQuery: {session1_query}")
        session1_response = result1["messages"][-1].content if result1["messages"] else "(empty)"
        print(f"Response: {session1_response[:500]}")
        print(f"\nMessages in state: {len(result1['messages'])}")
    except Exception as e:
        logger.error("Session 1 failed: %s", e)
        print(f"Session 1 error: {e}")
        return

    # ── SIMULATE RESTART ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SIMULATING RESTART — Clearing in-memory variables...")
    print("=" * 70)

    # Clear local references to simulate a fresh process
    del result1
    session1_response = None

    # Re-create app from scratch (simulates process restart)
    memory2 = SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
    app2 = build_graph(checkpointer=memory2)

    # ── SESSION 2: Follow-up using same thread_id ─────────────────
    print("\n" + "=" * 70)
    print("SESSION 2: Follow-up query (same thread_id)")
    print("=" * 70)

    session2_query = (
        "Based on what you found earlier about SKU-001, should we place a reorder? "
        "What was the stock level you reported?"
    )

    try:
        result2 = app2.invoke(
            {
                "messages": [HumanMessage(content=session2_query)],
                "current_sku": "SKU-001",
                "reorder_decision": "",
            },
            config=config,
        )

        print(f"\nQuery: {session2_query}")
        session2_response = result2["messages"][-1].content if result2["messages"] else "(empty)"
        print(f"Response: {session2_response[:500]}")
        print(f"\nTotal messages in state: {len(result2['messages'])}")
    except Exception as e:
        logger.error("Session 2 failed: %s", e)
        print(f"Session 2 error: {e}")
        return

    # ── VERIFICATION ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PERSISTENCE VERIFICATION")
    print("=" * 70)

    msg_count = len(result2["messages"])
    print(f"Total messages across both sessions: {msg_count}")
    print(f"Memory persisted: {'YES' if msg_count > 2 else 'NO'}")
    print(f"Checkpoint DB: {CHECKPOINT_DB}")
    print(f"Thread ID: {thread_id}")

    if msg_count > 2:
        print("\n✅ SUCCESS: State was persisted and restored across sessions.")
    else:
        print("\n⚠️  WARNING: State may not have persisted correctly.")


if __name__ == "__main__":
    main()
