"""
graph.py — LangGraph ReAct agent loop for the Dynamic Inventory Reorder Agent.

Builds a single-agent ReAct loop that binds an LLM to inventory tools,
using StateGraph with conditional routing between agent and tool nodes.
"""

import logging
import operator
from typing import Annotated, Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from tools import ALL_TOOLS

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """State schema for the ReAct agent graph."""
    messages: Annotated[list[BaseMessage], operator.add]
    current_sku: str
    reorder_decision: str


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert Inventory Reorder Agent for an electronics retailer.
Your job is to monitor stock levels, forecast demand, identify the best suppliers,
and generate purchase orders when reordering is necessary.

When asked to check inventory for a SKU:
1. First check current inventory levels using get_current_inventory
2. If stock is low, get historical sales data using get_sales_data
3. Forecast future demand using forecast_demand
4. Query supplier catalogs for pricing using query_supplier_catalog
5. Calculate optimal order quantity using calculate_order_qty
6. Generate a purchase order using generate_purchase_order
7. Send alerts for critical situations using send_alert

Always provide clear reasoning for your decisions. Be thorough and systematic."""


def create_agent_node(tools: list) -> callable:
    """Create an agent node function that binds the LLM to the given tools.

    Args:
        tools: List of LangChain tools to bind to the LLM.

    Returns:
        A function that processes the agent state.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState) -> dict[str, Any]:
        """Process the current state and decide on the next action."""
        from langchain_core.messages import SystemMessage

        messages = state["messages"]

        # Prepend system prompt if not already present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

        try:
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error("Agent node failed: %s", e)
            from langchain_core.messages import AIMessage
            return {"messages": [AIMessage(content=f"Error: {e}")]}

    return agent_node


def router(state: AgentState) -> str:
    """Route to tools if the last message has tool calls, otherwise end.

    Args:
        state: Current agent state.

    Returns:
        'tools' if there are pending tool calls, END otherwise.
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_graph(checkpointer: Any = None) -> Any:
    """Build and compile the ReAct agent graph.

    Args:
        checkpointer: Optional checkpointer for state persistence.

    Returns:
        Compiled LangGraph application.
    """
    agent_node = create_agent_node(ALL_TOOLS)
    tool_node = ToolNode(ALL_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", router, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    app = graph.compile(**compile_kwargs)
    logger.info("ReAct agent graph compiled successfully.")
    return app


# Build the default app instance
app = build_graph()


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    test_query = (
        "Check inventory for SKU-001 and determine if we need to reorder. "
        "If yes, calculate the optimal order quantity and identify the best supplier."
    )
    print(f"Test query: {test_query}\n")

    result = app.invoke({
        "messages": [HumanMessage(content=test_query)],
        "current_sku": "SKU-001",
        "reorder_decision": "",
    })

    print("\n=== Final Response ===")
    for msg in result["messages"]:
        print(f"[{msg.type}] {msg.content[:300] if msg.content else '(tool call)'}")
