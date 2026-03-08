"""
run_multi_agent.py — Runs the multi-agent collaboration and saves a full trace.

Executes the Inventory Researcher → Procurement Analyst pipeline for SKU-003
and writes the full conversation trace to collaboration_trace.log.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TRACE_LOG = Path(__file__).parent / "collaboration_trace.log"


def main() -> None:
    """Run the multi-agent scenario and save the collaboration trace."""
    from multi_agent_graph import build_multi_agent_graph

    app = build_multi_agent_graph()

    test_query = (
        "Research the current inventory situation for SKU-003 (Bluetooth Speaker), "
        "then generate a purchase order for the recommended quantity."
    )

    print("=" * 70)
    print("MULTI-AGENT COLLABORATION — Inventory Researcher + Procurement Analyst")
    print("=" * 70)
    print(f"\nScenario: {test_query}\n")
    print("-" * 70)

    trace_lines: list[str] = []
    trace_lines.append(f"{'='*70}")
    trace_lines.append("MULTI-AGENT COLLABORATION TRACE")
    trace_lines.append(f"Timestamp: {datetime.now().isoformat()}")
    trace_lines.append(f"Query: {test_query}")
    trace_lines.append(f"{'='*70}\n")

    try:
        result = app.invoke({
            "messages": [HumanMessage(content=test_query)],
            "current_sku": "SKU-003",
            "reorder_decision": "",
            "agent_a_output": "",
            "handover_complete": False,
            "final_recommendation": "",
        })

        for i, msg in enumerate(result["messages"]):
            role = msg.type.upper()
            content = msg.content if msg.content else ""

            # Identify which agent phase we're in
            if i == 0:
                phase = "USER INPUT"
            elif "RESEARCH_COMPLETE" in content:
                phase = "AGENT A (Inventory Researcher) — FINAL"
            elif hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_names = [tc["name"] for tc in msg.tool_calls]
                research_tool_names = {"get_sales_data", "get_current_inventory", "forecast_demand", "query_supplier_catalog"}
                if set(tool_names) & research_tool_names:
                    phase = "AGENT A (Inventory Researcher) — Tool Call"
                else:
                    phase = "AGENT B (Procurement Analyst) — Tool Call"
            elif role == "TOOL":
                phase = "TOOL RESPONSE"
            else:
                phase = "AGENT B (Procurement Analyst)" if result.get("handover_complete") else "AGENT A (Inventory Researcher)"

            entry = f"[Step {i+1}] {phase} | {role}"
            print(f"\n{entry}")
            trace_lines.append(entry)

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_line = f"  → Tool: {tc['name']}({tc['args']})"
                    print(tc_line)
                    trace_lines.append(tc_line)
            elif content:
                display = content[:500]
                print(f"  {display}")
                trace_lines.append(f"  {content}")

            trace_lines.append("")

        # Write trace to file
        with open(TRACE_LOG, "w") as f:
            f.write("\n".join(trace_lines))

        print(f"\n{'='*70}")
        print(f"Trace saved to: {TRACE_LOG}")
        print(f"{'='*70}")

        # Print final recommendation
        if result["messages"]:
            final = result["messages"][-1]
            print(f"\n{'='*70}")
            print("FINAL RECOMMENDATION")
            print(f"{'='*70}")
            print(final.content if final.content else "(No final content)")

    except Exception as e:
        logger.error("Multi-agent execution failed: %s", e)
        trace_lines.append(f"\nERROR: {e}")
        with open(TRACE_LOG, "w") as f:
            f.write("\n".join(trace_lines))
        raise


if __name__ == "__main__":
    main()
