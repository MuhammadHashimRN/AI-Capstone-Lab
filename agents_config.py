"""
agents_config.py — Defines two specialized agent personas for multi-agent orchestration.

Agent A (Inventory Researcher): Gathers data — stock levels, sales history, forecasts, supplier info.
Agent B (Procurement Analyst): Makes decisions — calculates order quantities, generates POs, sends alerts.
"""

import logging
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class AgentPersona:
    """Configuration for a specialized agent in the multi-agent system."""
    name: str
    role: str
    goal: str
    backstory: str
    system_prompt: str
    tool_names: list[str] = field(default_factory=list)


AGENT_A = AgentPersona(
    name="Inventory Researcher",
    role="Inventory Research Specialist",
    goal="Gather comprehensive data about stock levels, demand patterns, and supplier options",
    backstory=(
        "You are an experienced inventory analyst with 10 years of experience in "
        "electronics supply chain management. You excel at data gathering and analysis, "
        "identifying trends, and providing accurate research summaries."
    ),
    system_prompt=(
        "You are an Inventory Research Specialist. Your ONLY job is to gather data: "
        "check stock levels, analyze sales history, forecast demand, and query supplier catalogs. "
        "You NEVER generate purchase orders or send communications. "
        "Always be thorough — check inventory first, then get sales data for the last 90 days, "
        "forecast demand for the next 30 days, and query the supplier catalog for pricing. "
        "Always end your response with 'RESEARCH_COMPLETE' when you have gathered all necessary data."
    ),
    tool_names=["get_sales_data", "get_current_inventory", "forecast_demand", "query_supplier_catalog"],
)

AGENT_B = AgentPersona(
    name="Procurement Analyst",
    role="Procurement Decision Analyst",
    goal="Make optimal purchasing decisions based on research data and generate purchase orders",
    backstory=(
        "You are a senior procurement analyst specializing in cost optimization and "
        "supplier relationship management. You make data-driven purchasing decisions "
        "and ensure all orders follow company policy."
    ),
    system_prompt=(
        "You are a Procurement Decision Analyst. You receive research data from the "
        "Inventory Researcher and your job is to calculate optimal order quantities, "
        "generate purchase orders, and send alerts. You do NOT query databases directly. "
        "Based on the research provided to you:\n"
        "1. Calculate the optimal order quantity using the EOQ formula\n"
        "2. Generate a purchase order for the recommended quantity\n"
        "3. Send an alert if the situation is critical\n"
        "Use the data provided by the Inventory Researcher to inform your decisions."
    ),
    tool_names=["calculate_order_qty", "generate_purchase_order", "send_alert"],
)


if __name__ == "__main__":
    print("Agent A Configuration:")
    print(f"  Name: {AGENT_A.name}")
    print(f"  Role: {AGENT_A.role}")
    print(f"  Tools: {AGENT_A.tool_names}")
    print(f"  System Prompt: {AGENT_A.system_prompt[:100]}...")
    print()
    print("Agent B Configuration:")
    print(f"  Name: {AGENT_B.name}")
    print(f"  Role: {AGENT_B.role}")
    print(f"  Tools: {AGENT_B.tool_names}")
    print(f"  System Prompt: {AGENT_B.system_prompt[:100]}...")
