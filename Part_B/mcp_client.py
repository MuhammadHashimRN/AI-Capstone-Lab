"""
Part B Task 2: MCP Client Implementation
==========================================
Connects to the MCP server, discovers tools, invokes them via MCP protocol,
and displays structured responses. Uses Groq LLM as the model layer.
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"


async def run_mcp_client():
    """
    MCP Client pipeline:
      1. Establish connection to MCP server
      2. Discover available tools
      3. Pass tool schemas to the LLM as context
      4. LLM decides which tool to call
      5. Execute tool via MCP protocol
      6. Display structured response
    """
    print("=" * 60)
    print("MCP Client — Tool Discovery & Invocation Demo")
    print("=" * 60)

    # ─── Step 1: Connect to MCP Server ───────────────────────────────────
    server_script = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    print("\n[1] Connecting to MCP Server...")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the session
            await session.initialize()
            print("    Connection established successfully.")

            # ─── Step 2: Discover Tools ──────────────────────────────
            print("\n[2] Discovering tools from MCP Server...")
            tools_response = await session.list_tools()
            available_tools = tools_response.tools

            print(f"    Found {len(available_tools)} tools:")
            tool_schemas = []
            for tool in available_tools:
                print(f"      - {tool.name}: {tool.description[:80]}...")
                tool_schemas.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                })

            # ─── Step 3: Context Passing to LLM ─────────────────────
            print("\n[3] Passing tool context to LLM...")

            tool_context = json.dumps(tool_schemas, indent=2)
            system_prompt = f"""You are a helpful assistant with access to the following tools via MCP:

{tool_context}

When the user asks a question, determine which tool to call and provide the
tool name and arguments in this exact JSON format:
{{"tool_name": "<name>", "arguments": {{...}}}}

Respond with ONLY the JSON tool call, nothing else."""

            # ─── Step 4: User Queries & Tool Invocation ──────────────
            test_queries = [
                "What's the weather forecast for Islamabad for the next 5 days?",
                "Convert 1000 USD to PKR",
                "What is the distance between Lahore and Karachi?",
            ]

            for query in test_queries:
                print(f"\n{'─' * 50}")
                print(f"[User]: {query}")

                # Ask LLM to decide tool call
                llm = ChatGroq(
                    api_key=GROQ_API_KEY,
                    model=GROQ_MODEL,
                    temperature=0,
                )

                response = llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=query),
                ])

                llm_output = response.content.strip()
                print(f"[LLM Decision]: {llm_output[:200]}")

                # Parse the tool call from LLM response
                try:
                    # Extract JSON from response (handle markdown code blocks)
                    json_str = llm_output
                    if "```" in json_str:
                        json_str = json_str.split("```")[1]
                        if json_str.startswith("json"):
                            json_str = json_str[4:]
                    tool_call = json.loads(json_str.strip())
                    tool_name = tool_call["tool_name"]
                    tool_args = tool_call["arguments"]
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[Error] Could not parse tool call: {e}")
                    continue

                # ─── Step 5: Execute Tool via MCP ────────────────────
                print(f"[MCP Call]: {tool_name}({json.dumps(tool_args)})")

                result = await session.call_tool(tool_name, arguments=tool_args)

                # ─── Step 6: Display Structured Response ─────────────
                print(f"[MCP Response]:")
                for content_block in result.content:
                    if hasattr(content_block, "text"):
                        try:
                            parsed = json.loads(content_block.text)
                            print(json.dumps(parsed, indent=2))
                        except json.JSONDecodeError:
                            print(content_block.text)

    print(f"\n{'=' * 60}")
    print("[DONE] MCP Client demo completed successfully.")
    print("\nDemonstrated:")
    print("  ✓ Tool registration (server exposes 3 tools)")
    print("  ✓ Tool discovery (client lists available tools)")
    print("  ✓ Context passing (tool schemas sent to LLM)")
    print("  ✓ Tool invocation (LLM decides, client calls via MCP)")
    print("  ✓ Response handling (structured JSON responses)")


if __name__ == "__main__":
    if not GROQ_API_KEY:
        print("[ERROR] GROQ_API_KEY not set. Export it as an environment variable.")
        print("  export GROQ_API_KEY='your-key-here'")
        sys.exit(1)

    asyncio.run(run_mcp_client())
