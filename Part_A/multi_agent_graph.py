"""
Lab 4: Multi-Agent Orchestration (Specialized Teams)
=====================================================
Implements a two-agent architecture using LangGraph:
  - Procurement Analyst Agent: gathers data, forecasts demand, selects suppliers
  - Order Manager Agent: generates purchase orders based on analyst's recommendations

State handover is managed via LangGraph's conditional routing.
"""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE, enable_langsmith
from tools import PROCUREMENT_TOOLS, ORDER_EXECUTION_TOOLS
from agents_config import AGENT_PERSONAS

# Enable LangSmith tracing if API key is configured
enable_langsmith()


# ─── Multi-Agent State ──────────────────────────────────────────────────────

class MultiAgentState(TypedDict):
    """State schema for the multi-agent system.
    Tracks messages and which agent is currently active."""
    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str


# ─── LLM Factory ────────────────────────────────────────────────────────────

def get_agent_llm(agent_key: str):
    """Create an LLM instance bound to the tools allowed for a specific agent."""
    persona = AGENT_PERSONAS[agent_key]
    allowed_tool_names = set(persona["allowed_tools"])

    if agent_key == "procurement_analyst":
        tools = [t for t in PROCUREMENT_TOOLS if t.name in allowed_tool_names]
    else:
        tools = [t for t in ORDER_EXECUTION_TOOLS if t.name in allowed_tool_names]

    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=GROQ_TEMPERATURE,
    )
    return llm.bind_tools(tools), tools


# ─── Agent Nodes ────────────────────────────────────────────────────────────

def procurement_analyst_node(state: MultiAgentState) -> dict:
    """Procurement Analyst Agent: analyzes inventory, forecasts demand,
    evaluates suppliers, and calculates order quantities."""
    persona = AGENT_PERSONAS["procurement_analyst"]
    llm, _ = get_agent_llm("procurement_analyst")

    messages = list(state["messages"])
    # Inject system prompt for this agent
    sys_msg = SystemMessage(content=persona["system_prompt"])
    messages_with_system = [sys_msg] + [m for m in messages if not isinstance(m, SystemMessage)]

    response = llm.invoke(messages_with_system)
    return {"messages": [response], "current_agent": "procurement_analyst"}


def order_manager_node(state: MultiAgentState) -> dict:
    """Order Manager Agent: reviews analyst's recommendations and
    generates purchase orders."""
    persona = AGENT_PERSONAS["order_manager"]
    llm, _ = get_agent_llm("order_manager")

    messages = list(state["messages"])
    sys_msg = SystemMessage(content=persona["system_prompt"])
    messages_with_system = [sys_msg] + [m for m in messages if not isinstance(m, SystemMessage)]

    response = llm.invoke(messages_with_system)
    return {"messages": [response], "current_agent": "order_manager"}


# ─── Tool Nodes (restricted per agent) ──────────────────────────────────────

procurement_tool_node = ToolNode(tools=PROCUREMENT_TOOLS)
order_tool_node = ToolNode(tools=ORDER_EXECUTION_TOOLS)


# ─── Routing Logic ──────────────────────────────────────────────────────────

def route_procurement_analyst(state: MultiAgentState) -> str:
    """Route after Procurement Analyst's response:
    - If tool calls → procurement_tools
    - If 'ANALYSIS COMPLETE' in response → hand over to order_manager
    - Otherwise → END"""
    last_msg = state["messages"][-1]

    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "procurement_tools"

    if isinstance(last_msg, AIMessage) and last_msg.content:
        if "ANALYSIS COMPLETE" in last_msg.content.upper():
            return "order_manager"

    return END


def route_order_manager(state: MultiAgentState) -> str:
    """Route after Order Manager's response:
    - If tool calls → order_tools
    - Otherwise → END (order complete)"""
    last_msg = state["messages"][-1]

    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "order_tools"

    return END


# ─── Graph Construction ─────────────────────────────────────────────────────

def build_multi_agent_graph():
    """Build the multi-agent graph with handover logic.

    Flow:
        procurement_analyst → (tool calls?) → procurement_tools → procurement_analyst
                            → (analysis complete?) → order_manager
                            → (tool calls?) → order_tools → order_manager
                            → END
    """
    graph = StateGraph(MultiAgentState)

    # Add agent nodes
    graph.add_node("procurement_analyst", procurement_analyst_node)
    graph.add_node("order_manager", order_manager_node)

    # Add tool nodes
    graph.add_node("procurement_tools", procurement_tool_node)
    graph.add_node("order_tools", order_tool_node)

    # Entry point: always start with the Procurement Analyst
    graph.set_entry_point("procurement_analyst")

    # Procurement Analyst routing
    graph.add_conditional_edges(
        "procurement_analyst",
        route_procurement_analyst,
        {
            "procurement_tools": "procurement_tools",
            "order_manager": "order_manager",
            END: END,
        },
    )

    # After procurement tools execute, loop back to analyst
    graph.add_edge("procurement_tools", "procurement_analyst")

    # Order Manager routing
    graph.add_conditional_edges(
        "order_manager",
        route_order_manager,
        {
            "order_tools": "order_tools",
            END: END,
        },
    )

    # After order tools execute, loop back to order manager
    graph.add_edge("order_tools", "order_manager")

    compiled = graph.compile()
    return compiled


# ─── Demo / Test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os as _os

    print("=" * 60)
    print("Multi-Agent Inventory Reorder System — Demo")
    print("=" * 60)

    if not GROQ_API_KEY:
        print("[ERROR] GROQ_API_KEY not set.")
        exit(1)

    graph = build_multi_agent_graph()

    test_query = (
        "We need to reorder SKU-001 (Wireless Headphones X1). "
        "Please analyze the inventory situation, forecast demand, "
        "select the best supplier, and generate a purchase order."
    )

    print(f"\nUser: {test_query}\n")
    print("-" * 60)

    result = graph.invoke({
        "messages": [HumanMessage(content=test_query)],
        "current_agent": "procurement_analyst",
    })

    # ── Build collaboration trace and write to log file ──────────────
    log_path = _os.path.join(_os.path.dirname(__file__), "collaboration_trace.log")
    log_lines = []
    log_lines.append("=" * 70)
    log_lines.append("COLLABORATION TRACE — Multi-Agent Inventory Reorder System")
    log_lines.append("=" * 70)
    log_lines.append(f"\n[User Request]: {test_query}\n")

    for i, msg in enumerate(result["messages"]):
        if isinstance(msg, HumanMessage):
            line = f"[Step {i}] USER: {msg.content}"
            log_lines.append(line)
        elif isinstance(msg, SystemMessage):
            continue
        elif isinstance(msg, AIMessage) and msg.tool_calls:
            agent = "PROCUREMENT ANALYST" if any(
                tc["name"] in AGENT_PERSONAS["procurement_analyst"]["allowed_tools"]
                for tc in msg.tool_calls
            ) else "ORDER MANAGER"
            log_lines.append(f"\n[Step {i}] {agent} -> Tool Calls:")
            if msg.content:
                log_lines.append(f"  Thought: {msg.content[:500]}")
            for tc in msg.tool_calls:
                log_lines.append(f"  -> Calling: {tc['name']}({str(tc['args'])[:200]})")
        elif hasattr(msg, "name") and msg.name:
            log_lines.append(f"\n[Step {i}] TOOL RESULT ({msg.name}): {str(msg.content)[:300]}")
        elif isinstance(msg, AIMessage):
            content = msg.content or "(empty)"
            if "ANALYSIS COMPLETE" in content.upper():
                log_lines.append(f"\n{'~' * 70}")
                log_lines.append(f"[Step {i}] *** HANDOVER: Procurement Analyst -> Order Manager ***")
                log_lines.append(f"{'~' * 70}")
                log_lines.append(f"  Procurement Analyst Output:\n  {content[:800]}")
            else:
                log_lines.append(f"\n[Step {i}] ORDER MANAGER (Final Output):\n  {content[:800]}")

    log_lines.append(f"\n{'=' * 70}")
    log_lines.append("[DONE] Multi-agent collaboration completed successfully.")
    log_lines.append(f"{'=' * 70}")

    trace_text = "\n".join(log_lines)

    # Write to file
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(trace_text)
    print(f"\n[LOG] Collaboration trace saved to: {log_path}")

    # Also print to console
    print(trace_text)
