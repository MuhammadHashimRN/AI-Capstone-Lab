"""
Lab 10: Breaking Change Demonstration — Intentionally Degraded Agent
=====================================================================
This module replaces graph.py's build_react_graph() with a broken
implementation that demonstrates what happens when the agent is degraded.

Degradation method: The agent never calls any tools and returns an empty
answer. This causes ALL three evaluation metrics to collapse to 0.0:
  - Faithfulness  = 0.0  (no answer → score_faithfulness returns 0.0 directly)
  - Relevancy     = 0.0  (no answer → score_relevancy returns 0.0 directly)
  - Tool Accuracy = 0.0  (no tools called → score_tool_accuracy returns 0.0)
All three fall below their thresholds → run_eval.py exits with code 1 (FAIL).

How the CI breaking change is triggered:
  The demo script ci_breaking_change_demo.py monkey-patches sys.modules so
  that `import graph` resolves to this module instead of the real graph.py.
  No files on disk are modified; the patch is applied in memory only and
  reversed after the broken evaluation completes.

Real-world equivalents of this kind of degradation:
  • Accidentally deleting the tools list binding (tools=[])
  • A merge conflict that zeroed out the system prompt
  • A refactor that broke the conditional edge so the agent always goes to END
    without reasoning
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Minimal state — mirrors the real AgentState so the eval harness works."""
    messages: Annotated[list[BaseMessage], add_messages]


def _broken_agent_node(state: AgentState) -> dict:
    """Returns an empty response with no tool calls.

    This simulates a corrupted agent: it receives the user's question but
    produces no useful output — no reasoning, no tool calls, no answer.
    The evaluation pipeline will score this as 0.0 across all metrics.
    """
    return {"messages": [AIMessage(content="")]}


def build_react_graph():
    """Build the BROKEN graph.

    The graph has a single node that returns empty responses.
    It exposes the same function signature as the real graph.py so the
    evaluation harness can import it transparently.
    """
    graph = StateGraph(AgentState)
    graph.add_node("agent", _broken_agent_node)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return graph.compile()
