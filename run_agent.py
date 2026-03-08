"""
run_agent.py — Runs the single-agent ReAct loop with a test query.

Invokes the LangGraph agent to check inventory for SKU-001 and determine
whether a reorder is needed.
"""

import logging

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the single-agent ReAct loop with a test inventory check."""
    from graph import app

    test_query = (
        "Check inventory for SKU-001 and determine if we need to reorder. "
        "If yes, calculate the optimal order quantity and identify the best supplier."
    )

    print("=" * 70)
    print("DYNAMIC INVENTORY REORDER AGENT — Single-Agent ReAct Loop")
    print("=" * 70)
    print(f"\nQuery: {test_query}\n")
    print("-" * 70)

    try:
        result = app.invoke({
            "messages": [HumanMessage(content=test_query)],
            "current_sku": "SKU-001",
            "reorder_decision": "",
        })

        print("\n" + "=" * 70)
        print("CONVERSATION TRACE")
        print("=" * 70)

        for i, msg in enumerate(result["messages"]):
            role = msg.type.upper()
            content = msg.content if msg.content else "(tool call/response)"
            print(f"\n[{i+1}] {role}:")

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"  → Tool Call: {tc['name']}({tc['args']})")
            else:
                print(f"  {content[:500]}")

        print("\n" + "=" * 70)
        print("FINAL ANSWER")
        print("=" * 70)
        final_msg = result["messages"][-1]
        print(final_msg.content if final_msg.content else "(No final content)")

    except Exception as e:
        logger.error("Agent execution failed: %s", e)
        raise


if __name__ == "__main__":
    main()
