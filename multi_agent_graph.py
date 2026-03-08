"""
multi_agent_graph.py — Multi-agent LangGraph with two specialized agents.

Agent A (Inventory Researcher) gathers data, then hands off to
Agent B (Procurement Analyst) who makes purchasing decisions.
"""

import logging
import operator
from typing import Annotated, Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agents_config import AGENT_A, AGENT_B
from tools import PROCUREMENT_TOOLS, RESEARCH_TOOLS

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extended State
# ---------------------------------------------------------------------------

class MultiAgentState(TypedDict):
    """State for the multi-agent orchestration graph."""
    messages: Annotated[list[BaseMessage], operator.add]
    current_sku: str
    reorder_decision: str
    agent_a_output: str
    handover_complete: bool
    final_recommendation: str


# ---------------------------------------------------------------------------
# Agent Nodes
# ---------------------------------------------------------------------------

def create_agent_a_node() -> callable:
    """Create the Inventory Researcher agent node.

    Returns:
        A function that processes state for Agent A.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    llm_with_tools = llm.bind_tools(RESEARCH_TOOLS)

    def agent_a_node(state: MultiAgentState) -> dict[str, Any]:
        """Agent A: Research inventory data."""
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=AGENT_A.system_prompt)] + messages

        try:
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error("Agent A failed: %s", e)
            return {"messages": [AIMessage(content=f"Agent A Error: {e}")]}

    return agent_a_node


def create_agent_b_node() -> callable:
    """Create the Procurement Analyst agent node.

    Returns:
        A function that processes state for Agent B.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    llm_with_tools = llm.bind_tools(PROCUREMENT_TOOLS)

    def agent_b_node(state: MultiAgentState) -> dict[str, Any]:
        """Agent B: Make procurement decisions."""
        messages = state["messages"]

        # If this is the first time Agent B runs, inject the handover context
        if not state.get("handover_complete"):
            agent_a_output = state.get("agent_a_output", "")
            if agent_a_output:
                handover_msg = HumanMessage(
                    content=(
                        f"The Inventory Researcher has completed their analysis. "
                        f"Here is their research summary:\n\n{agent_a_output}\n\n"
                        f"Based on this research, please calculate the optimal order quantity, "
                        f"generate a purchase order, and send any necessary alerts."
                    )
                )
                messages = [SystemMessage(content=AGENT_B.system_prompt), handover_msg]

        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=AGENT_B.system_prompt)] + messages

        try:
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error("Agent B failed: %s", e)
            return {"messages": [AIMessage(content=f"Agent B Error: {e}")]}

    return agent_b_node


# ---------------------------------------------------------------------------
# Router Functions
# ---------------------------------------------------------------------------

def router_after_agent_a(state: MultiAgentState) -> str:
    """Route after Agent A: check for tool calls or RESEARCH_COMPLETE signal.

    Args:
        state: Current multi-agent state.

    Returns:
        Next node name or END.
    """
    last_message = state["messages"][-1]

    # If Agent A has tool calls, route to research tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "research_tools"

    # If Agent A signals completion, route to Agent B
    content = last_message.content if last_message.content else ""
    if "RESEARCH_COMPLETE" in content:
        return "handover"

    # Default: end (shouldn't normally reach here)
    return "handover"


def router_after_agent_b(state: MultiAgentState) -> str:
    """Route after Agent B: check for tool calls or completion.

    Args:
        state: Current multi-agent state.

    Returns:
        Next node name or END.
    """
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "procurement_tools"

    return END


def handover_node(state: MultiAgentState) -> dict[str, Any]:
    """Transfer context from Agent A to Agent B.

    Extracts Agent A's final output and sets up the handover.

    Args:
        state: Current multi-agent state.

    Returns:
        Updated state with handover information.
    """
    # Collect Agent A's research output
    agent_a_messages = []
    for msg in state["messages"]:
        if msg.content:
            agent_a_messages.append(msg.content)

    # Use last 3 messages to capture the final research summary with tool results
    agent_a_output = "\n".join(agent_a_messages[-3:])

    logger.info("=== HANDOVER: Agent A → Agent B ===")
    return {
        "agent_a_output": agent_a_output,
        "handover_complete": True,
        "messages": [],
    }


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_multi_agent_graph(checkpointer: Any = None) -> Any:
    """Build and compile the multi-agent LangGraph.

    Args:
        checkpointer: Optional checkpointer for state persistence.

    Returns:
        Compiled multi-agent LangGraph application.
    """
    agent_a = create_agent_a_node()
    agent_b = create_agent_b_node()
    research_tool_node = ToolNode(RESEARCH_TOOLS)
    procurement_tool_node = ToolNode(PROCUREMENT_TOOLS)

    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("agent_a", agent_a)
    graph.add_node("research_tools", research_tool_node)
    graph.add_node("handover", handover_node)
    graph.add_node("agent_b", agent_b)
    graph.add_node("procurement_tools", procurement_tool_node)

    # Set entry point
    graph.set_entry_point("agent_a")

    # Agent A routing
    graph.add_conditional_edges(
        "agent_a",
        router_after_agent_a,
        {
            "research_tools": "research_tools",
            "handover": "handover",
        },
    )
    graph.add_edge("research_tools", "agent_a")

    # Handover → Agent B
    graph.add_edge("handover", "agent_b")

    # Agent B routing
    graph.add_conditional_edges(
        "agent_b",
        router_after_agent_b,
        {
            "procurement_tools": "procurement_tools",
            END: END,
        },
    )
    graph.add_edge("procurement_tools", "agent_b")

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    app = graph.compile(**compile_kwargs)
    logger.info("Multi-agent graph compiled successfully.")
    return app


if __name__ == "__main__":
    app = build_multi_agent_graph()

    test_query = (
        "Research the current inventory situation for SKU-003 (Bluetooth Speaker), "
        "then generate a purchase order for the recommended quantity."
    )

    print("=" * 70)
    print("MULTI-AGENT ORCHESTRATION TEST")
    print("=" * 70)
    print(f"\nQuery: {test_query}\n")

    result = app.invoke({
        "messages": [HumanMessage(content=test_query)],
        "current_sku": "SKU-003",
        "reorder_decision": "",
        "agent_a_output": "",
        "handover_complete": False,
        "final_recommendation": "",
    })

    for i, msg in enumerate(result["messages"]):
        print(f"\n[{i+1}] {msg.type.upper()}: {msg.content[:300] if msg.content else '(tool call)'}")
