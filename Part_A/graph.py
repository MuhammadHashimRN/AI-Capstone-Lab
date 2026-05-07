"""
Lab 3: The Reasoning Loop (Powered by LangGraph)
=================================================
Implements a ReAct (Reason + Act) loop for the Dynamic Inventory Reorder Agent.
Defines the state graph, agent node, tool node, and conditional routing.
"""

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE, enable_langsmith
from tools import ALL_TOOLS

# Enable LangSmith tracing if API key is configured
enable_langsmith()


# ─── Graph State Definition ─────────────────────────────────────────────────

class AgentState(TypedDict):
    """State schema for the inventory reorder agent.
    Stores the message history (thoughts and actions) for the ReAct loop."""
    messages: Annotated[list[BaseMessage], add_messages]


# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the Dynamic Inventory Reorder Agent, an autonomous AI system
that manages inventory procurement for an electronics retailer.

Your responsibilities:
1. Monitor inventory levels and identify items below reorder points.
2. Analyze historical sales data and forecast future demand.
3. Evaluate and select the best supplier using multi-criteria scoring.
4. Calculate optimal order quantities using EOQ models.
5. Generate purchase orders for approval.

When a user asks about inventory or reordering:
- First check current inventory levels using get_current_inventory.
- If stock is below the reorder point, retrieve sales data with get_sales_data.
- Forecast demand using forecast_demand.
- Query suppliers with query_all_suppliers or select_best_supplier.
- Calculate optimal order quantity with calculate_order_quantity.
- Generate a purchase order with generate_purchase_order if needed.

Always explain your reasoning at each step. Be precise with numbers and data.
Use the query_knowledge_base tool to search for additional context when needed."""


# ─── LLM Initialization ─────────────────────────────────────────────────────

def get_llm(tools=None):
    """Initialize the Groq LLM with optional tool binding."""
    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=GROQ_TEMPERATURE,
    )
    if tools:
        llm = llm.bind_tools(tools)
    return llm


# ─── Node Definitions ───────────────────────────────────────────────────────

def agent_node(state: AgentState) -> dict:
    """The Agent Node: takes the current state, calls the LLM with tools,
    and returns the next action (tool call or final answer)."""
    llm = get_llm(tools=ALL_TOOLS)

    # Prepend system prompt if not already present
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    response = llm.invoke(messages)
    return {"messages": [response]}


# Tool node: executes tool calls identified by the agent
tool_node = ToolNode(tools=ALL_TOOLS)


# ─── Conditional Router ─────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    """The Conditional Router: checks the LLM's last message.
    - If tool calls are present → route to 'tools' node.
    - If final answer (no tool calls) → route to END."""
    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


# ─── Graph Construction ─────────────────────────────────────────────────────

def build_react_graph():
    """Build and compile the ReAct loop graph.

    Flow:
        agent → (has tool calls?) → tools → agent → ... → END
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    # Set entry point
    graph.set_entry_point("agent")

    # Add conditional edge: agent decides whether to use tools or finish
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})

    # After tools execute, loop back to agent for further reasoning
    graph.add_edge("tools", "agent")

    compiled = graph.compile()
    return compiled


# ─── Demo / Test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Dynamic Inventory Reorder Agent — ReAct Loop Demo")
    print("=" * 60)

    if not GROQ_API_KEY:
        print("[ERROR] GROQ_API_KEY not set. Export it as an environment variable.")
        print("  export GROQ_API_KEY='your-key-here'")
        exit(1)

    graph = build_react_graph()

    # Test query: check inventory and recommend reorder for SKU-001
    test_query = (
        "Check the inventory level for SKU-001 (Wireless Headphones X1). "
        "If it needs reordering, analyze the sales data, forecast demand "
        "for the next 30 days, and recommend the best supplier."
    )

    print(f"\nUser: {test_query}\n")
    print("-" * 60)

    result = graph.invoke({"messages": [HumanMessage(content=test_query)]})

    # Print the conversation trace
    for msg in result["messages"]:
        role = msg.__class__.__name__.replace("Message", "")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            print(f"\n[{role}] Reasoning + Tool Calls:")
            if msg.content:
                print(f"  Thought: {msg.content[:200]}")
            for tc in msg.tool_calls:
                print(f"  -> Calling: {tc['name']}({tc['args']})")
        elif hasattr(msg, "name") and msg.name:
            print(f"\n[Tool: {msg.name}] Result: {str(msg.content)[:200]}...")
        elif isinstance(msg, AIMessage):
            print(f"\n[Agent Final Answer]:\n{msg.content}")
        elif isinstance(msg, HumanMessage):
            print(f"\n[User]: {msg.content}")

    print("\n" + "=" * 60)
    print("[DONE] ReAct loop completed successfully.")
