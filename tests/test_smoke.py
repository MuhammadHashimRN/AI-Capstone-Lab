"""Smoke tests — verify the project layout is intact and core modules import."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repo_layout():
    assert (ROOT / "Part_A").is_dir()
    assert (ROOT / "Part_B").is_dir()
    assert (ROOT / "Technical_Report.md").is_file()
    assert (ROOT / "PRD.md").is_file()
    assert (ROOT / "requirements.txt").is_file()


def test_part_a_key_modules_present():
    part_a = ROOT / "Part_A"
    for fname in (
        "app.py",
        "multi_agent_graph.py",
        "agents_config.py",
        "tools.py",
        "guardrails_config.py",
        "approval_logic.py",
        "ingest_data.py",
        "Dockerfile",
    ):
        assert (part_a / fname).is_file(), f"missing {fname}"


def test_part_b_mcp_modules_present():
    part_b = ROOT / "Part_B"
    for fname in ("mcp_server.py", "mcp_client.py"):
        assert (part_b / fname).is_file(), f"missing {fname}"


def test_requirements_lists_core_deps():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for dep in ("langgraph", "langchain", "chromadb", "fastapi", "streamlit"):
        assert dep in reqs, f"requirements.txt missing {dep}"
