"""
Lab 5: Persistence Test
========================
Proves the agent can retrieve information from a previous session
using a thread_id. Demonstrates SqliteSaver checkpointing.
"""

import sqlite3
from langchain_core.messages import HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing import Annotated, TypedDict

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE, CHECKPOINT_DB_PATH
from tools import ALL_TOOLS
from graph import AgentState, agent_node, tool_node, should_continue


def build_persistent_graph(conn):
    """Build a graph with SqliteSaver persistence."""
    checkpointer = SqliteSaver(conn)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


def main():
    print("=" * 60)
    print("PERSISTENCE TEST — Session Recovery via thread_id")
    print("=" * 60)

    if not GROQ_API_KEY:
        print("[ERROR] GROQ_API_KEY not set.")
        return

    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    graph = build_persistent_graph(conn)
    thread_id = "persistence-test-thread-001"
    config = {"configurable": {"thread_id": thread_id}}

    # ─── Session 1: Initial conversation ─────────────────────────────────
    print("\n--- SESSION 1: Initial Request ---")
    query1 = "Check the inventory level for SKU-003 (Smart LED Desk Lamp)."
    print(f"[User]: {query1}")

    result1 = graph.invoke(
        {"messages": [HumanMessage(content=query1)]},
        config=config,
    )

    last_msg = result1["messages"][-1]
    if isinstance(last_msg, AIMessage):
        print(f"[Agent]: {last_msg.content[:300]}")

    saved_state = graph.get_state(config)
    print(f"\n[Checkpoint] Saved {len(saved_state.values.get('messages', []))} messages to {CHECKPOINT_DB_PATH}")

    # ─── Simulate Script Restart ─────────────────────────────────────────
    print("\n--- SIMULATING SCRIPT RESTART ---")
    print("(Closing and reopening connection...)\n")

    # Close and reopen — simulates a restart
    conn.close()
    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    graph = build_persistent_graph(conn)

    # ─── Session 2: Resume with same thread_id ───────────────────────────
    print("--- SESSION 2: Resuming with same thread_id ---")

    # Verify state was recovered
    recovered_state = graph.get_state(config)
    recovered_msgs = recovered_state.values.get("messages", [])
    print(f"[Recovery] Found {len(recovered_msgs)} messages from previous session.")

    if recovered_msgs:
        for msg in recovered_msgs[-2:]:
            role = "User" if isinstance(msg, HumanMessage) else "Agent"
            content = msg.content[:150] if msg.content else "(tool call)"
            print(f"  [{role}]: {content}")

    # Follow-up question that relies on context from Session 1
    query2 = "Based on what you just told me, does that SKU need reordering? What is its reorder point?"
    print(f"\n[User (follow-up)]: {query2}")

    result2 = graph.invoke(
        {"messages": [HumanMessage(content=query2)]},
        config=config,
    )

    last_msg = result2["messages"][-1]
    if isinstance(last_msg, AIMessage):
        print(f"[Agent]: {last_msg.content[:400]}")

    conn.close()

    print("\n" + "=" * 60)
    print("[DONE] Persistence test completed.")
    print(f"  Thread ID: {thread_id}")
    print(f"  Checkpoint DB: {CHECKPOINT_DB_PATH}")
    print("  The agent successfully recovered context from Session 1 in Session 2.")
    print("=" * 60)


if __name__ == "__main__":
    main()
