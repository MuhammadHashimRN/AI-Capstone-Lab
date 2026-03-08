"""
approval_logic.py — Human-in-the-Loop (HITL) safety interrupt for purchase orders.

Implements an approval workflow that pauses before generating purchase orders,
allowing the user to Proceed, Cancel, or Edit the proposed order.
"""

import logging
import operator
from typing import Annotated, Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from tools import (
    ALL_TOOLS,
    calculate_order_qty,
    forecast_demand,
    generate_purchase_order,
    get_current_inventory,
    get_sales_data,
    query_supplier_catalog,
    send_alert,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State with proposed order
# ---------------------------------------------------------------------------

class ApprovalState(TypedDict):
    """State schema for the HITL approval workflow."""
    messages: Annotated[list[BaseMessage], operator.add]
    current_sku: str
    reorder_decision: str
    proposed_order: dict


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert Inventory Reorder Agent. When asked to check inventory:
1. Check current inventory with get_current_inventory
2. Get sales data with get_sales_data
3. Forecast demand with forecast_demand
4. Query supplier catalog with query_supplier_catalog
5. Calculate order quantity with calculate_order_qty
6. Generate a purchase order with generate_purchase_order
7. Send alerts if needed with send_alert

Be thorough and systematic in your analysis."""


def create_agent_node() -> callable:
    """Create the agent node for the approval workflow.

    Returns:
        Agent node function.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    # Exclude generate_purchase_order from auto-tools; it goes through approval
    pre_approval_tools = [
        get_sales_data,
        get_current_inventory,
        forecast_demand,
        query_supplier_catalog,
        calculate_order_qty,
        send_alert,
    ]
    llm_with_tools = llm.bind_tools(pre_approval_tools + [generate_purchase_order])

    def agent_node(state: ApprovalState) -> dict[str, Any]:
        """Process state and decide next action."""
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

        try:
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error("Agent node failed: %s", e)
            return {"messages": [AIMessage(content=f"Error: {e}")]}

    return agent_node


def purchase_order_node(state: ApprovalState) -> dict[str, Any]:
    """Execute the generate_purchase_order tool after approval.

    This node is the one that gets interrupted for HITL approval.

    Args:
        state: Current state with proposed order.

    Returns:
        Updated state with PO result.
    """
    proposed = state.get("proposed_order", {})
    if not proposed:
        # Extract from last tool call
        for msg in reversed(state["messages"]):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "generate_purchase_order":
                        proposed = tc["args"]
                        break
            if proposed:
                break

    if proposed:
        result = generate_purchase_order.invoke(proposed)
        return {
            "messages": [AIMessage(content=f"Purchase Order Generated: {result}")],
            "proposed_order": proposed,
        }

    return {"messages": [AIMessage(content="No purchase order to generate.")]}


def router(state: ApprovalState) -> str:
    """Route based on tool calls, with special handling for purchase orders.

    Args:
        state: Current state.

    Returns:
        Next node name or END.
    """
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Check if any tool call is generate_purchase_order
        for tc in last_message.tool_calls:
            if tc["name"] == "generate_purchase_order":
                return "purchase_order_node"
        return "tools"

    return END


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_approval_graph() -> Any:
    """Build the HITL approval workflow graph.

    Returns:
        Compiled graph with interrupt_before on purchase_order_node.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    from pathlib import Path

    checkpoint_path = Path(__file__).parent / "approval_checkpoint.sqlite"
    memory = SqliteSaver.from_conn_string(str(checkpoint_path))

    agent = create_agent_node()
    # Tool node for all tools EXCEPT generate_purchase_order
    pre_approval_tools = [
        get_sales_data,
        get_current_inventory,
        forecast_demand,
        query_supplier_catalog,
        calculate_order_qty,
        send_alert,
    ]
    tool_node = ToolNode(pre_approval_tools)

    graph = StateGraph(ApprovalState)
    graph.add_node("agent", agent)
    graph.add_node("tools", tool_node)
    graph.add_node("purchase_order_node", purchase_order_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        router,
        {"tools": "tools", "purchase_order_node": "purchase_order_node", END: END},
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("purchase_order_node", "agent")

    # Compile with interrupt BEFORE purchase order generation
    app = graph.compile(
        checkpointer=memory,
        interrupt_before=["purchase_order_node"],
    )
    logger.info("Approval workflow graph compiled with HITL interrupt.")
    return app, memory


def display_approval_prompt(state: dict) -> None:
    """Display the proposed purchase order for human approval.

    Args:
        state: Current graph state with proposed order details.
    """
    proposed = state.get("proposed_order", {})

    # Try to extract from pending tool calls
    if not proposed:
        for msg in reversed(state.get("messages", [])):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "generate_purchase_order":
                        proposed = tc["args"]
                        break
            if proposed:
                break

    sku = proposed.get("sku", "Unknown")
    qty = proposed.get("quantity", 0)
    supplier = proposed.get("supplier_name", "Unknown")
    price = proposed.get("unit_price", 0.0)
    total = round(qty * price, 2)

    print("\n" + "=" * 50)
    print("       === APPROVAL REQUIRED ===")
    print("=" * 50)
    print(f"  SKU:        {sku}")
    print(f"  Quantity:   {qty} units")
    print(f"  Supplier:   {supplier}")
    print(f"  Unit Price: ${price:.2f}")
    print(f"  Total Cost: ${total:,.2f}")
    print("=" * 50)
    print("  [P]roceed / [C]ancel / [E]dit")
    print("=" * 50)


def main() -> None:
    """Run the HITL approval workflow interactively."""
    app, memory = build_approval_graph()

    thread_id = "approval-thread-001"
    config = {"configurable": {"thread_id": thread_id}}

    query = (
        "Check inventory for SKU-001 and if reorder is needed, calculate the "
        "optimal order quantity and generate a purchase order."
    )

    print("=" * 70)
    print("HUMAN-IN-THE-LOOP APPROVAL WORKFLOW")
    print("=" * 70)
    print(f"\nQuery: {query}\n")

    try:
        # Run until the interrupt point
        result = app.invoke(
            {
                "messages": [HumanMessage(content=query)],
                "current_sku": "SKU-001",
                "reorder_decision": "",
                "proposed_order": {},
            },
            config=config,
        )

        # Check if we hit the interrupt
        snapshot = app.get_state(config)
        pending_tasks = snapshot.next if hasattr(snapshot, "next") else ()

        if "purchase_order_node" in pending_tasks:
            display_approval_prompt(result)

            choice = input("\nYour choice: ").strip().upper()

            if choice == "P":
                print("\n✅ Proceeding with purchase order...")
                result = app.invoke(None, config=config)
                print("\nPurchase order completed.")

            elif choice == "C":
                print("\n❌ Purchase order CANCELLED.")
                logger.info("PO cancelled by user for thread %s", thread_id)
                with open(str(Path(__file__).parent / "alerts.log"), "a") as f:
                    f.write(f"PO CANCELLED by user for thread {thread_id}\n")

            elif choice == "E":
                print("\n✏️  Edit mode:")
                new_qty = input("  New quantity (or Enter to keep): ").strip()
                new_supplier = input("  New supplier (or Enter to keep): ").strip()

                # Build updated order from current state
                current_order = result.get("proposed_order", {})
                for msg in reversed(result.get("messages", [])):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if tc["name"] == "generate_purchase_order":
                                current_order = tc["args"]
                                break
                    if current_order:
                        break

                if new_qty:
                    current_order["quantity"] = int(new_qty)
                if new_supplier:
                    current_order["supplier_name"] = new_supplier

                # Update state and resume
                app.update_state(config, {"proposed_order": current_order})
                print(f"\n  Updated order: {current_order}")
                result = app.invoke(None, config=config)
                print("\n✅ Purchase order completed with edits.")

            else:
                print("Invalid choice. Cancelling.")
        else:
            print("\nAgent completed without requiring purchase order approval.")

        # Print final messages
        if result and result.get("messages"):
            print(f"\n{'='*70}")
            print("FINAL STATE")
            print(f"{'='*70}")
            final = result["messages"][-1]
            print(final.content if final.content else "(No content)")

    except Exception as e:
        logger.error("Approval workflow failed: %s", e)
        raise


if __name__ == "__main__":
    main()
