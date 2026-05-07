"""
Lab 5: State Management & Human-in-the-Loop (HITL)
====================================================
Implements:
  - Persistent memory using SqliteSaver checkpointer
  - Safety interruption before high-risk actions (purchase order generation)
  - Human approval/cancellation/editing of agent's proposed actions
  - Session recovery using thread identifiers
"""

import json
import sqlite3
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE, CHECKPOINT_DB_PATH, enable_langsmith
from tools import ALL_TOOLS

# Enable LangSmith tracing if API key is configured
enable_langsmith()


# ─── State Definition ───────────────────────────────────────────────────────

class HITLAgentState(TypedDict):
    """State for the HITL-enabled agent with persistent checkpointing."""
    messages: Annotated[list[BaseMessage], add_messages]


# ─── System Prompt ───────────────────────────────────────────────────────────

HITL_SYSTEM_PROMPT = """You are the Dynamic Inventory Reorder Agent with Human-in-the-Loop safety.

You help manage inventory by analyzing stock levels, forecasting demand, selecting suppliers,
and generating purchase orders. However, for SAFETY, you MUST use the generate_purchase_order
tool to create purchase orders — this action will be paused for human approval before execution.

Follow the standard workflow:
1. Check inventory → 2. Analyze sales → 3. Forecast demand → 4. Select supplier
→ 5. Calculate order quantity → 6. Generate purchase order (requires human approval)

Always explain your reasoning clearly at each step."""


# ─── Node Definitions ───────────────────────────────────────────────────────

def agent_node(state: HITLAgentState) -> dict:
    """Agent reasoning node with tool binding."""
    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=GROQ_TEMPERATURE,
    ).bind_tools(ALL_TOOLS)

    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=HITL_SYSTEM_PROMPT)] + list(messages)

    response = llm.invoke(messages)
    return {"messages": [response]}


# Safe tools: all tools EXCEPT generate_purchase_order
safe_tools = [t for t in ALL_TOOLS if t.name != "generate_purchase_order"]
# High-risk tools: only generate_purchase_order
risky_tools = [t for t in ALL_TOOLS if t.name == "generate_purchase_order"]

safe_tool_node = ToolNode(tools=safe_tools)
risky_tool_node = ToolNode(tools=risky_tools)


# ─── Routing Logic ──────────────────────────────────────────────────────────

def route_agent(state: HITLAgentState) -> str:
    """Route based on the agent's last message:
    - Tool calls with generate_purchase_order → 'risky_tools' (will be interrupted)
    - Other tool calls → 'safe_tools'
    - No tool calls → END"""
    last_msg = state["messages"][-1]

    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == "generate_purchase_order":
                return "risky_tools"
        return "safe_tools"

    return END


# ─── Graph Construction ─────────────────────────────────────────────────────

def build_hitl_graph():
    """Build the HITL-enabled graph with:
    - SqliteSaver for persistent checkpointing
    - interrupt_before on risky_tools node for human approval
    """
    # Initialize persistent checkpointer
    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    graph = StateGraph(HITLAgentState)

    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("safe_tools", safe_tool_node)
    graph.add_node("risky_tools", risky_tool_node)

    # Entry point
    graph.set_entry_point("agent")

    # Conditional routing from agent
    graph.add_conditional_edges(
        "agent",
        route_agent,
        {
            "safe_tools": "safe_tools",
            "risky_tools": "risky_tools",
            END: END,
        },
    )

    # After tools, loop back to agent
    graph.add_edge("safe_tools", "agent")
    graph.add_edge("risky_tools", "agent")

    # Compile with checkpointer and interrupt_before risky_tools
    compiled = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["risky_tools"],  # HITL: pause before PO generation
    )

    return compiled, conn


# ─── Interactive HITL Demo ───────────────────────────────────────────────────

def run_hitl_demo():
    """Interactive demo showing:
    1. Agent processes a reorder request
    2. Pauses before generating purchase order
    3. Human reviews, edits, and approves/cancels
    4. Session persistence with thread_id recovery
    """
    print("=" * 60)
    print("HITL Agent — Human-in-the-Loop Demo")
    print("=" * 60)

    if not GROQ_API_KEY:
        print("[ERROR] GROQ_API_KEY not set.")
        return

    graph, conn = build_hitl_graph()
    thread_id = "hitl-demo-thread-001"
    config = {"configurable": {"thread_id": thread_id}}

    # Step 1: Send the initial request
    user_query = (
        "Check inventory for SKU-001 and if it needs reordering, "
        "analyze sales, forecast demand, select the best supplier, "
        "calculate order quantity, and generate a purchase order."
    )

    print(f"\n[User]: {user_query}")
    print("-" * 60)

    result = graph.invoke(
        {"messages": [HumanMessage(content=user_query)]},
        config=config,
    )

    # Print intermediate results
    for msg in result["messages"]:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"\n  [Agent] Calling: {tc['name']}")
        elif isinstance(msg, AIMessage) and msg.content:
            print(f"\n  [Agent]: {msg.content[:300]}")

    # Step 2: Check if we hit the interrupt (paused before risky_tools)
    current_state = graph.get_state(config)

    if current_state.next and "risky_tools" in current_state.next:
        print("\n" + "=" * 60)
        print("[!] SAFETY INTERRUPTION: Purchase Order Requires Approval")
        print("=" * 60)

        # Show the proposed action
        last_msg = current_state.values["messages"][-1]
        if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] == "generate_purchase_order":
                    print(f"\n  Proposed Action: {tc['name']}")
                    print(f"  Parameters:")
                    for k, v in tc["args"].items():
                        print(f"    {k}: {v}")

        # Step 3: Demonstrate state editing — human modifies the order quantity
        print("\n[Human Review] Editing proposed order quantity from agent's suggestion to 250...")

        # Get current state values and modify the tool call arguments
        current_values = current_state.values
        messages = list(current_values["messages"])

        # Find and edit the last AI message with the PO tool call
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage) and messages[i].tool_calls:
                for tc in messages[i].tool_calls:
                    if tc["name"] == "generate_purchase_order":
                        tc["args"]["quantity"] = 250  # Human edits the quantity
                        print(f"  [Edited] quantity -> 250")
                break

        # Update the state with edited values
        graph.update_state(config, {"messages": messages})

        # Step 4: Resume execution (human approves)
        print("\n[Human]: APPROVED — Proceeding with edited order.\n")
        print("-" * 60)

        result = graph.invoke(None, config=config)

        # Print final results
        for msg in result["messages"][-3:]:
            if isinstance(msg, AIMessage) and msg.content:
                print(f"\n  [Agent]: {msg.content[:400]}")
            elif hasattr(msg, "name") and msg.name:
                print(f"\n  [Tool: {msg.name}]: {str(msg.content)[:300]}")

    else:
        print("\n[INFO] Agent completed without triggering safety interrupt.")

    # Step 5: Demonstrate session recovery
    print("\n" + "=" * 60)
    print("SESSION RECOVERY TEST")
    print("=" * 60)
    print(f"Thread ID: {thread_id}")

    # Simulate restarting — retrieve saved state
    recovered_state = graph.get_state(config)
    msg_count = len(recovered_state.values.get("messages", []))
    print(f"Recovered {msg_count} messages from checkpoint.")
    print(f"Checkpoint DB: {CHECKPOINT_DB_PATH}")

    # Send a follow-up message using the same thread
    followup = "What was the last purchase order you generated?"
    print(f"\n[User (follow-up)]: {followup}")

    result = graph.invoke(
        {"messages": [HumanMessage(content=followup)]},
        config=config,
    )

    last_response = result["messages"][-1]
    if isinstance(last_response, AIMessage):
        print(f"\n  [Agent]: {last_response.content[:400]}")

    conn.close()
    print("\n" + "=" * 60)
    print("[DONE] HITL demo completed successfully.")


if __name__ == "__main__":
    run_hitl_demo()
