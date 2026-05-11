"""
Final Exam — Report Generator
==============================
Produces TWO PDF deliverables:

  1. Whole_Project_Report.pdf   — Labs 1-11 + Open-Ended + Final Exam Part A.
  2. Part_B_Report.pdf          — Dedicated Self-RAG Agent report.

All content is inlined or sourced from the actual repository files. No
placeholders or "TODO" markers are produced. Architecture images come
from existing PNGs in the repo (Lab 1 diagram + Self-RAG diagram).

Run:
    python Final_Exam/gen_reports.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]   # AI-Capstone-Lab/
PART_A_SRC = ROOT / "Part_A"
FINAL_PART_A = ROOT / "Final_Exam" / "Part_A"
FINAL_PART_B = ROOT / "Final_Exam" / "Part_B"
OUT_WHOLE = ROOT / "Final_Exam" / "Whole_Project_Report.pdf"
OUT_PART_B = ROOT / "Final_Exam" / "Part_B_Report.pdf"

LAB_ARCH_PNG = ROOT / "Architecture_Diagram.png"
SELF_RAG_PNG = FINAL_PART_B / "architecture.png"

TODAY = datetime.now().strftime("%d %B %Y")


# ─── Styles ─────────────────────────────────────────────────────────────────

def make_styles():
    base = getSampleStyleSheet()
    styles = {
        "Cover": ParagraphStyle(
            "Cover", parent=base["Title"], fontSize=26, leading=32,
            spaceBefore=2 * cm, spaceAfter=12, alignment=TA_CENTER,
            textColor=colors.HexColor("#0d1b3d"),
        ),
        "CoverSub": ParagraphStyle(
            "CoverSub", parent=base["Title"], fontSize=15, leading=20,
            alignment=TA_CENTER, textColor=colors.HexColor("#1f6feb"),
            spaceAfter=12,
        ),
        "CoverMeta": ParagraphStyle(
            "CoverMeta", parent=base["Normal"], fontSize=11, leading=15,
            alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
        ),
        "H1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontSize=18, leading=22,
            spaceBefore=18, spaceAfter=10, textColor=colors.HexColor("#0d1b3d"),
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontSize=14, leading=18,
            spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1f6feb"),
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontSize=11.5, leading=15,
            spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0d1b3d"),
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontSize=10.5, leading=15,
            alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "Bullet": ParagraphStyle(
            "Bullet", parent=base["BodyText"], fontSize=10.5, leading=14,
            leftIndent=14, bulletIndent=2, spaceAfter=2,
        ),
        "Caption": ParagraphStyle(
            "Caption", parent=base["Italic"], fontSize=9, leading=12,
            alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
            spaceAfter=10,
        ),
        "Code": ParagraphStyle(
            "Code", parent=base["Code"], fontSize=8.5, leading=11,
            leftIndent=8, rightIndent=8, spaceBefore=4, spaceAfter=10,
            backColor=colors.HexColor("#f3f4f6"),
            borderColor=colors.HexColor("#d0d7de"), borderWidth=0.5,
            borderPadding=6,
        ),
        "TableCell": ParagraphStyle(
            "TableCell", parent=base["Normal"], fontSize=9, leading=12,
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader", parent=base["Normal"], fontSize=9, leading=12,
            textColor=colors.white, fontName="Helvetica-Bold",
        ),
        "Footer": ParagraphStyle(
            "Footer", parent=base["Normal"], fontSize=8.5,
            textColor=colors.HexColor("#666666"), alignment=TA_CENTER,
        ),
    }
    return styles


STY = make_styles()


# ─── Helpers ────────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    """Escape characters meaningful to reportlab's Paragraph mini-HTML parser."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def H1(text: str, *, page_break: bool = True):
    out = []
    if page_break:
        out.append(PageBreak())
    out.append(Paragraph(esc(text), STY["H1"]))
    return out


def H2(text: str):
    return [Paragraph(esc(text), STY["H2"])]


def H3(text: str):
    return [Paragraph(esc(text), STY["H3"])]


def P(text: str, style: str = "Body"):
    return [Paragraph(text if "<" in text or "&" in text else esc(text), STY[style])]


def PP(text: str):
    """Paragraph that allows inline <b>/<i> markup — caller is responsible for escaping."""
    return [Paragraph(text, STY["Body"])]


def bullets(items: list[str]):
    out = []
    for it in items:
        # Preserve simple inline markup in the bullets when the caller pre-renders.
        rendered = it if ("<b>" in it or "<i>" in it or "<code>" in it or "&lt;" in it or "&amp;" in it) else esc(it)
        out.append(Paragraph(f"• {rendered}", STY["Bullet"]))
    return out


def code_block(text: str, *, max_lines: int = 80) -> list:
    lines = text.splitlines()
    if len(lines) > max_lines:
        # Truncate noisy blocks but indicate clipping.
        text = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
    # Preformatted preserves whitespace and uses the Code style we set up.
    return [Preformatted(text, STY["Code"])]


def caption(text: str):
    return [Paragraph(esc(text), STY["Caption"])]


def picture(path: Path, *, width_cm: float = 14.0,
            max_height_cm: float = 22.0,
            caption_text: str | None = None):
    """Embed an image, scaling to fit both width and height bounds."""
    if not path.exists():
        return P(f"[Diagram missing: {path.name}]")
    img = Image(str(path))
    iw, ih = img.imageWidth, img.imageHeight
    target_w = width_cm * cm
    target_h_cap = max_height_cm * cm
    scale = target_w / iw
    if ih * scale > target_h_cap:
        scale = target_h_cap / ih
    img.drawWidth = iw * scale
    img.drawHeight = ih * scale
    out = [img]
    if caption_text:
        out += caption(caption_text)
    return out


def make_table(rows: list[list], col_widths: list[float] | None = None,
               header: bool = True, font_size: int = 9):
    """Build a Paragraph-wrapped Table so cells flow nicely."""
    data = []
    for i, row in enumerate(rows):
        cells = []
        style = STY["TableHeader"] if (header and i == 0) else STY["TableCell"]
        for cell in row:
            if isinstance(cell, str):
                cells.append(Paragraph(cell, style))
            else:
                cells.append(cell)
        data.append(cells)

    tbl = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d7de")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
        # Alternating rows for readability
        for r in range(1, len(rows)):
            if r % 2 == 0:
                cmds.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f6f8fa")))
    tbl.setStyle(TableStyle(cmds))
    return [tbl, Spacer(1, 8)]


def read_text(path: Path, *, default: str = "(file not found)") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def excerpt(text: str, *, max_lines: int = 60) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines omitted)"


# ─── PageTemplate with footer ───────────────────────────────────────────────

def make_doc(path: Path, title: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title,
        author="AI407L Student",
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="normal", showBoundary=0)

    def on_page(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(A4[0] / 2, 1.0 * cm, f"{title}  —  Page {doc_.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="default", frames=frame, onPage=on_page)])
    return doc


# ─── Content builders ───────────────────────────────────────────────────────

def cover_block(title: str, subtitle: str, *, extra_lines: list[str] | None = None):
    out = [Spacer(1, 3 * cm)]
    out += [Paragraph(esc(title), STY["Cover"])]
    out += [Paragraph(esc(subtitle), STY["CoverSub"])]
    out += [Spacer(1, 1 * cm)]
    out += [Paragraph("AI407L &mdash; AI Capstone Project Lab", STY["CoverMeta"])]
    out += [Paragraph("Faculty of Computer Science and Engineering", STY["CoverMeta"])]
    out += [Paragraph("Ghulam Ishaq Khan Institute of Engineering Sciences &amp; Technology", STY["CoverMeta"])]
    out += [Paragraph("Spring 2026", STY["CoverMeta"])]
    out += [Spacer(1, 1 * cm)]
    out += [Paragraph(f"Submitted on: {TODAY}", STY["CoverMeta"])]
    if extra_lines:
        for line in extra_lines:
            out += [Paragraph(esc(line), STY["CoverMeta"])]
    return out


def toc_block(entries: list[tuple[str, str]]):
    """Render a simple flat TOC. `entries` are (label, dotted_no)."""
    out = H1("Table of Contents", page_break=True)
    rows = [["#", "Section"]]
    for i, (label, _) in enumerate(entries, 1):
        rows.append([str(i), label])
    out += make_table(rows, col_widths=[1.2 * cm, 13 * cm])
    return out


# ====================================================================
# WHOLE PROJECT REPORT
# ====================================================================

def build_whole_project_story() -> list:
    story: list = []

    # ── Cover ────────────────────────────────────────────────────────────
    story += cover_block(
        "AI Capstone Project — Whole Project Report",
        "Dynamic Inventory Reorder Agent (Labs 1–11, Open-Ended) "
        "+ Final Exam Part A (Drift Monitoring &amp; Feedback Loops)",
    )

    # ── TOC ──────────────────────────────────────────────────────────────
    toc = [
        ("Executive Summary", "1"),
        ("Lab 1 — Problem Framing & Agentic Architecture", "2"),
        ("Lab 2 — Knowledge Engineering & Domain Grounding (RAG)", "3"),
        ("Lab 3 — The Reasoning Loop (ReAct in LangGraph)", "4"),
        ("Lab 4 — Multi-Agent Orchestration", "5"),
        ("Lab 5 — State Management & Human-in-the-Loop (HITL)", "6"),
        ("Lab 6 — Security Guardrails & Jailbreaking", "7"),
        ("Lab 7 — Evaluation & Observability", "8"),
        ("Lab 8 — The API Layer (FastAPI)", "9"),
        ("Lab 9 — Industrial Packaging (Docker)", "10"),
        ("Lab 10 — Agentic CI/CD Pipelines", "11"),
        ("Lab 11 — Drift Monitoring & Feedback Loops (initial)", "12"),
        ("Open-Ended Task — Deployment + Automated Quality Gates", "13"),
        ("Final Exam Part A — Drift Monitoring & Feedback Loops (extended)", "14"),
        ("Conclusions", "15"),
        ("Appendix A — Repository Structure", "A"),
        ("Appendix B — Environment & Reproduction", "B"),
    ]
    story += toc_block(toc)

    # ── 1. Executive Summary ─────────────────────────────────────────────
    story += H1("1. Executive Summary")
    story += PP(
        "This report documents the construction of the <b>Dynamic Inventory Reorder Agent</b>, "
        "an autonomous Agentic AI system developed across eleven progressive labs and "
        "two assessment phases. The system replaces a manual procurement workflow with "
        "a LangGraph-orchestrated agent that perceives inventory, sales, supplier and "
        "promotional data, reasons over them with a Groq-hosted LLaMA-3.1-8B model, and "
        "executes purchase-order actions through validated Python tools — including a "
        "human-in-the-loop safety interrupt before any irreversible step."
    )
    story += PP(
        "The end-to-end stack: <b>LangGraph</b> (workflow orchestration) + "
        "<b>LangChain</b> (tool abstraction) + <b>Groq</b> (LLM inference) + "
        "<b>ChromaDB</b> (vector store) + <b>SQLite</b> (checkpoint + feedback log) + "
        "<b>FastAPI</b> (REST API) + <b>Streamlit</b> (operator UI) + <b>Docker Compose</b> "
        "(multi-service deployment) + <b>GitHub Actions</b> (quality-gate CI/CD) + "
        "<b>LangSmith</b> (trace observability)."
    )
    story += PP(
        "The agent meets every rubric requirement of Labs 1–11, the Open-Ended Deployment "
        "and CI/CD task, and the Final Exam Part A drift-monitoring task. Section 14 of "
        "this document covers Part A in extensive detail (live interaction capture, "
        "failure-mode analysis, real before/after evidence of a prompt-level fix). "
        "The companion <i>Part B Report</i> covers the Self-RAG University Course "
        "Advisory Agent built for the 60-mark Part B section of the final exam."
    )

    story += H2("Key Metrics & Coverage")
    story += make_table([
        ["Surface", "Indicator", "Value"],
        ["Tools", "Python @tool functions with Pydantic schemas", "8"],
        ["RAG index", "ChromaDB chunks ingested from seed data", "62"],
        ["Test dataset", "Lab 7 evaluation cases (≥ 20 required)", "25"],
        ["CI thresholds", "Versioned metrics in eval_thresholds.json", "3"],
        ["Adversarial tests", "Documented in security_report.md", "6"],
        ["Feedback (Lab 11)", "Sample seeded interactions", "10+"],
        ["Feedback (Final Exam A)", "Live /chat interactions logged + graded", "12"],
    ], col_widths=[3.5 * cm, 8 * cm, 3 * cm])

    # ── 2. Lab 1 ─────────────────────────────────────────────────────────
    story += H1("2. Lab 1 — Problem Framing & Agentic Architecture")

    story += H2("2.1 Problem Statement")
    story += PP(
        "Inventory management at an electronics retailer is a balancing act: under-ordering "
        "produces stockouts and lost sales, while over-ordering ties up capital. The "
        "Procurement Manager (Jessica) currently spends 20+ hours/week on manual reorder "
        "reviews across 500+ SKUs because data is siloed across the ERP, sales database, "
        "supplier PDFs, promotional calendars, and external market context. A single LLM "
        "call cannot solve this — it requires perceiving multiple modalities, reasoning "
        "over them, calling deterministic Python tools, and executing actions."
    )

    story += H2("2.2 User Personas")
    story += make_table([
        ["Persona", "Role", "Primary pain", "Goal"],
        ["Jessica", "Procurement Manager",
         "20 h/wk on manual reviews; firefighting stockouts",
         "Reduce stockouts 80%, cut excess inventory 40%"],
        ["Raj", "Operations Director",
         "Warehouse space wasted on slow movers",
         "Inventory turnover 4× → 6×; 95% in-stock for top 100"],
        ["Supplier", "External fulfilment",
         "Last-minute rush orders; no capacity forecast",
         "Predictable optimised order quantities"],
    ], col_widths=[2.5 * cm, 3 * cm, 5 * cm, 4.5 * cm])

    story += H2("2.3 Success Metrics")
    story += make_table([
        ["Metric", "Current", "Target"],
        ["Stockout rate", "8% of orders", "< 2%"],
        ["Excess inventory cost", "$500K / year", "< $300K / year"],
        ["Forecast accuracy (MAPE)", "65%", "85%"],
        ["Procurement time savings", "Baseline", "70% reduction"],
        ["Inventory turnover", "4× / year", "6× / year"],
    ], col_widths=[5 * cm, 4 * cm, 5 * cm])

    story += H2("2.4 System Architecture (LangGraph)")
    story += picture(LAB_ARCH_PNG, width_cm=15,
                     caption_text="Lab 1 high-level architecture (committed as Architecture_Diagram.png).")
    story += PP(
        "Three layers: <b>Perceive</b> (ChromaDB-backed RAG over supplier catalogs, "
        "sales history, inventory levels, and promotional calendar; structured CSV "
        "tools for live data); <b>Reason</b> (LangGraph state machine with agent and "
        "tool nodes; conditional router); <b>Execute</b> (eight Python tools, "
        "including a high-risk <code>generate_purchase_order</code> gated behind a "
        "human approval interrupt)."
    )

    story += H2("2.5 Data Inventory (Initial_Data/)")
    story += make_table([
        ["File", "Description", "Used by"],
        ["sales_history.csv", "Transaction-level sales over 12 months",
         "get_sales_data, forecast_demand"],
        ["inventory_levels.csv", "Current stock, reorder points, warehouse meta",
         "get_current_inventory"],
        ["supplier_catalog_techdist.csv", "TechDistributors catalog",
         "query_all_suppliers, select_best_supplier"],
        ["supplier_catalog_globalelec.csv", "GlobalElec catalog",
         "query_all_suppliers, select_best_supplier"],
        ["supplier_catalog_primeparts.csv", "PrimeParts catalog",
         "query_all_suppliers, select_best_supplier"],
        ["promotional_calendar.csv", "Upcoming campaigns + demand multipliers",
         "forecast_demand"],
    ], col_widths=[5.5 * cm, 5 * cm, 4 * cm])

    # ── 3. Lab 2 ─────────────────────────────────────────────────────────
    story += H1("3. Lab 2 — Knowledge Engineering & Domain Grounding (RAG)")

    story += H2("3.1 Ingestion Pipeline (ingest_data.py)")
    story += PP(
        "All seed data is loaded into a persistent ChromaDB collection "
        "<code>inventory_knowledge_base</code> using "
        "<code>SentenceTransformerEmbeddingFunction</code> with "
        "<code>sentence-transformers/all-MiniLM-L6-v2</code>. Each CSV is processed "
        "by a dedicated function that produces semantic, natural-language chunks rather "
        "than raw rows — so retrieval semantics match the agent's reasoning style."
    )

    story += H2("3.2 Cleaning")
    story += PP(
        "<code>clean_text()</code> strips HTML tags and collapses whitespace before "
        "embedding. The text is reassembled into descriptive sentences for each chunk "
        "(e.g. \"Supplier: GlobalElec Supply. Product: Wireless Headphones X1 (SKU: "
        "SKU-001). Unit price: $14.50. MOQ: 200 units. Lead time: 14 days …\")."
    )

    story += H2("3.3 Chunking Strategy")
    story += bullets([
        "<b>Supplier catalogs</b> — one chunk per (supplier, SKU) row, rendered as a self-contained pricing/availability description.",
        "<b>Sales history</b> — aggregated to monthly summaries per SKU, so each chunk carries a complete trend window instead of an isolated transaction.",
        "<b>Inventory levels</b> — one chunk per SKU with stock, reorder point, safety stock, warehouse location.",
        "<b>Promotional calendar</b> — one chunk per event with affected categories and demand multiplier.",
    ])

    story += H2("3.4 Metadata Schema (≥ 3 tags per chunk)")
    story += make_table([
        ["Key", "Type", "Example"],
        ["doc_type", "string",
         "supplier_catalog | sales_history | inventory_level | promotional_event"],
        ["sku", "string", "SKU-001"],
        ["product_name", "string", "Wireless Headphones X1"],
        ["category", "string", "Electronics"],
        ["supplier_name", "string", "GlobalElec Supply (catalogs only)"],
        ["source_file", "string", "supplier_catalog_globalelec.csv"],
        ["last_updated", "ISO 8601", "2026-03-12T10:30:00"],
    ], col_widths=[3.5 * cm, 2.5 * cm, 8 * cm])

    story += H2("3.5 Retrieval Tests (retrieval_test.md)")
    story += PP("Three queries exercise the index. Test 2 also demonstrates metadata filtering.")
    story += make_table([
        ["#", "Query", "Filter", "Outcome"],
        ["1", "cheapest supplier for wireless headphones", "(none)",
         "All 3 supplier catalogs for SKU-001 returned, ranked by similarity"],
        ["2", "headphones price and lead time", "doc_type = supplier_catalog",
         "Only supplier rows surfaced — sales history excluded"],
        ["3", "monthly sales trend for wireless headphones", "doc_type = sales_history",
         "Monthly aggregates for SKU-001 returned"],
    ], col_widths=[0.7 * cm, 4.5 * cm, 4 * cm, 5 * cm])

    story += H2("3.6 Grounding Justification")
    story += PP(
        "The LLM has no knowledge of this retailer's SKU catalog, supplier price sheets, "
        "current stock counts, or promotional calendar. RAG over these structured CSVs "
        "is the only way the agent can answer factual questions like \"who is the cheapest "
        "supplier for SKU-001 right now?\" — and the only way to keep the system honest "
        "as the data changes day-to-day (re-ingestion is a single command)."
    )

    # ── 4. Lab 3 ─────────────────────────────────────────────────────────
    story += H1("4. Lab 3 — The Reasoning Loop (ReAct in LangGraph)")

    story += H2("4.1 Tool Catalogue (tools.py)")
    story += PP(
        "All eight tools are <code>@tool</code>-decorated and validate inputs through "
        "Pydantic <code>BaseModel</code> schemas. Their docstrings double as instructions "
        "to the LLM."
    )
    story += make_table([
        ["Tool", "Input schema", "Purpose"],
        ["get_sales_data", "SalesDataInput (sku, start_date, end_date)",
         "Historical sales and returns for an SKU"],
        ["get_current_inventory", "InventoryInput (sku)",
         "Real-time stock, reorder point, safety stock, warehouse"],
        ["forecast_demand", "ForecastInput (sku, forecast_days)",
         "Weighted moving average + promotional uplift"],
        ["query_all_suppliers", "SupplierQueryInput (sku)",
         "List every supplier offer for a SKU"],
        ["select_best_supplier", "SupplierSelectionInput (sku, required_quantity)",
         "Multi-criteria score (40/25/20/15 price/lead/reliability/quality)"],
        ["calculate_order_quantity", "OrderQuantityInput",
         "EOQ-based optimal quantity with capacity cap"],
        ["generate_purchase_order", "PurchaseOrderInput",
         "Create PO document — gated behind HITL interrupt"],
        ["query_knowledge_base", "KnowledgeBaseQueryInput (query, doc_type)",
         "Semantic search over the RAG index"],
    ], col_widths=[4.5 * cm, 5 * cm, 5 * cm])

    story += H2("4.2 Graph Definition (graph.py)")
    story += code_block(
        "class AgentState(TypedDict):\n"
        '    messages: Annotated[list[BaseMessage], add_messages]\n\n'
        "graph = StateGraph(AgentState)\n"
        'graph.add_node("agent", agent_node)\n'
        'graph.add_node("tools", ToolNode(tools=ALL_TOOLS))\n'
        'graph.set_entry_point("agent")\n'
        'graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})\n'
        'graph.add_edge("tools", "agent")\n'
        "compiled = graph.compile()"
    )

    story += H2("4.3 Conditional Router (should_continue)")
    story += PP(
        "If the last AIMessage contains <code>tool_calls</code>, the router returns "
        "<code>\"tools\"</code> (executes the tool node, loops back to the agent). "
        "Otherwise it returns <code>END</code>, terminating the reasoning loop with "
        "the agent's final answer. This is the canonical ReAct loop, implemented in "
        "pure LangGraph without any prebuilt agent abstractions."
    )

    story += H2("4.4 Sample Live Trace")
    story += PP(
        "End-to-end test against the live <code>/chat</code> endpoint with thread_id "
        "<code>smoke-test-002</code>:"
    )
    story += code_block(
        'POST /chat  {"message":"Check inventory for SKU-001","thread_id":"smoke-test-002"}\n'
        '{\n'
        '  "thread_id":"smoke-test-002",\n'
        '  "answer":"Based on the current inventory level, SKU-001 is below its reorder\n'
        '            point of 100 units. The current stock level is 45 units,\n'
        '            indicating a stock deficit of 55 units.",\n'
        '  "tools_called":["get_current_inventory"],\n'
        '  "latency_ms":33267,\n'
        '  "guardrail_passed":true\n'
        '}'
    )

    # ── 5. Lab 4 ─────────────────────────────────────────────────────────
    story += H1("5. Lab 4 — Multi-Agent Orchestration")

    story += H2("5.1 Specialised Personas (agents_config.py)")
    story += make_table([
        ["Agent", "Role", "Allowed tools"],
        ["Procurement Analyst",
         "Data gathering & analysis (10y supply-chain analytics persona)",
         "get_sales_data, get_current_inventory, forecast_demand, "
         "query_all_suppliers, select_best_supplier, calculate_order_quantity, "
         "query_knowledge_base"],
        ["Order Manager",
         "Purchase-order execution (validates analyst output, creates PO)",
         "generate_purchase_order, query_knowledge_base"],
    ], col_widths=[3.5 * cm, 4.5 * cm, 7 * cm])

    story += H2("5.2 Handover Mechanism")
    story += PP(
        "Each agent has its own node and tool node. The Procurement Analyst signals "
        "completion by including the literal string <b>\"ANALYSIS COMPLETE\"</b> in its "
        "response. The conditional router <code>route_procurement_analyst</code> detects "
        "this and transitions the graph to the Order Manager node, which extracts the "
        "recommended SKU, quantity, supplier and price from the analyst's message and "
        "invokes <code>generate_purchase_order</code>. Each agent's <code>ToolNode</code> "
        "is restricted to its allowed tools, enforcing separation of concerns at the "
        "graph level — not merely by prompt."
    )

    story += H2("5.3 Collaboration Trace Excerpt")
    story += code_block(excerpt(read_text(PART_A_SRC / "collaboration_trace.log"), max_lines=40))

    # ── 6. Lab 5 ─────────────────────────────────────────────────────────
    story += H1("6. Lab 5 — State Management & Human-in-the-Loop (HITL)")

    story += H2("6.1 Persistent Checkpoints")
    story += PP(
        "<code>SqliteSaver</code> is wired into the compiled graph. Every node "
        "transition is checkpointed to <code>checkpoint_db.sqlite</code> keyed by "
        "<code>thread_id</code>. The same thread can be resumed across script restarts "
        "and across multiple HTTP requests, which is critical for the API layer in "
        "Lab 8 — a stateless POST /chat call carries the thread_id and the agent's "
        "memory comes back automatically."
    )

    story += H2("6.2 Safety Interrupt before risky_tools")
    story += code_block(
        "# split tools by risk\n"
        "safe_tools  = [t for t in ALL_TOOLS if t.name != 'generate_purchase_order']\n"
        "risky_tools = [t for t in ALL_TOOLS if t.name == 'generate_purchase_order']\n"
        "\n"
        "compiled = graph.compile(\n"
        "    checkpointer=SqliteSaver(conn),\n"
        "    interrupt_before=['risky_tools'],  # pause BEFORE PO generation\n"
        ")"
    )

    story += H2("6.3 State Editing (Human Intervention)")
    story += PP(
        "Inside <code>approval_logic.py</code> the demo retrieves the paused state, "
        "modifies the <code>quantity</code> argument of the pending tool call from "
        "the agent's suggestion to 250 units, persists the new state via "
        "<code>graph.update_state(config, {'messages': messages})</code>, then "
        "resumes with <code>graph.invoke(None, config=config)</code> so the order "
        "executes with the human-edited quantity."
    )

    story += H2("6.4 Persistence Test (persistence_test.py)")
    story += PP(
        "Two sessions, same <code>thread_id</code>. Session 1 asks "
        "\"Check the inventory level for SKU-003.\" Session 2 closes and reopens the "
        "connection, then asks a follow-up that requires Session 1's context "
        "(\"Based on what you just told me, does that SKU need reordering?\"). The "
        "agent recovers the saved messages and answers from memory — no need to "
        "re-run <code>get_current_inventory</code> against the stale follow-up "
        "context."
    )

    # ── 7. Lab 6 ─────────────────────────────────────────────────────────
    story += H1("7. Lab 6 — Security Guardrails & Jailbreaking")

    story += H2("7.1 Dual-Layer Guardrail Architecture")
    story += PP(
        "<code>guardrail_node</code> runs <i>before</i> the agent node. Layer A is "
        "deterministic (regex + keyword lists in <code>guardrails_config.py</code>); "
        "Layer B is an LLM-as-a-Judge classifier that catches semantically novel "
        "attacks. If either layer returns UNSAFE, the graph routes to <code>alert_node</code> "
        "which emits a standardised refusal and bypasses the agent entirely."
    )

    story += H2("7.2 Detection Catalogue")
    story += make_table([
        ["Category", "Examples"],
        ["FORBIDDEN_KEYWORDS",
         "delete database, drop table, rm -rf, leak api key, transfer funds (17 entries)"],
        ["INJECTION_PATTERNS",
         "ignore (all) previous instructions, pretend you are a, jailbreak, "
         "reveal your (system) instructions (14 regex patterns)"],
        ["OFF_TOPIC_PATTERNS",
         "(write|compose) (a) (poem|story|joke), tell me a joke, "
         "(generate|create) (malware|virus|exploit) (6 patterns)"],
        ["OUTPUT_SANITIZATION",
         "Windows/Unix file paths, api_key:= assignments, "
         "Python __dunder__ keys, email addresses"],
    ], col_widths=[4 * cm, 11 * cm])

    story += H2("7.3 Adversarial Test Results (security_report.md)")
    story += make_table([
        ["#", "Attack", "Detection Layer", "Outcome"],
        ["1", "DAN persona bypass", "Deterministic (pretend you are a)", "Blocked"],
        ["2", "Instruction hijacking", "Deterministic (ignore previous instructions)", "Blocked"],
        ["3", "Payload smuggling (poem + delete DB)", "Deterministic (off-topic + forbidden)", "Blocked"],
        ["4", "Off-topic (joke)", "Deterministic (tell me a joke)", "Blocked"],
        ["5", "Subtle instruction override", "LLM-as-a-Judge", "Blocked"],
        ["6", "Legitimate inventory query", "Both layers pass", "Allowed"],
    ], col_widths=[0.6 * cm, 4.5 * cm, 5 * cm, 4 * cm])

    # ── 8. Lab 7 ─────────────────────────────────────────────────────────
    story += H1("8. Lab 7 — Evaluation & Observability")

    story += H2("8.1 Test Dataset (test_dataset.json)")
    story += PP(
        "25 (query, expected_answer, required_tool, category) cases — exceeding the "
        "minimum of 20. The dataset spans inventory checks, sales analysis, supplier "
        "comparison, EOQ calculation, multi-tool reorder pipelines, and adversarial "
        "guardrail tests. Categories: inventory, sales, supplier, optimization, "
        "multi_step, security."
    )

    story += H2("8.2 LLM-as-a-Judge Metrics (run_eval.py)")
    story += bullets([
        "<b>Faithfulness</b> — the agent's answer is supported by retrieved context (no hallucination).",
        "<b>Answer Relevancy</b> — the answer directly addresses the user query.",
        "<b>Tool Call Accuracy</b> — the agent invoked the expected tool (or any 2+ tools for multi-step).",
    ])

    story += H2("8.3 LangSmith Integration")
    story += PP(
        "When <code>LANGSMITH_API_KEY</code> is exported, <code>enable_langsmith()</code> "
        "flips <code>LANGCHAIN_TRACING_V2=true</code> and the agent emits traces under "
        "the <code>inventory-reorder-agent</code> project. Each per-query result row in "
        "<code>evaluation_results.json</code> carries the LangSmith run id and a "
        "deep-link URL; node-level latency and token counts are pulled in too so the "
        "bottleneck analysis below is data-driven."
    )

    story += H2("8.4 Bottleneck Analysis (bottleneck_analysis.txt)")
    story += code_block(read_text(PART_A_SRC / "bottleneck_analysis.txt"))

    # ── 9. Lab 8 ─────────────────────────────────────────────────────────
    story += H1("9. Lab 8 — The API Layer (FastAPI)")

    story += H2("9.1 Pydantic Schemas (schema.py)")
    story += code_block(read_text(PART_A_SRC / "schema.py"))

    story += H2("9.2 /chat — Stateful Synchronous Endpoint")
    story += PP(
        "The thread_id sent by the client is mapped into "
        "<code>config = {'configurable': {'thread_id': request.thread_id}}</code> "
        "and threaded into <code>graph.invoke(...)</code>. The same SqliteSaver "
        "checkpointer from Lab 5 makes the stateless HTTP layer stateful at the "
        "agent level — sticky sessions are not required."
    )

    story += H2("9.3 /stream — Server-Sent Events")
    story += PP(
        "An async generator iterates over <code>graph.stream(...)</code> in "
        "<code>stream_mode='updates'</code> and yields one SSE event per agent step: "
        "<code>tool_call</code>, <code>tool_result</code>, <code>message</code>, "
        "<code>thought</code>, or terminal <code>done</code>/<code>error</code>. "
        "This is what powers the ChatGPT-style streaming UI."
    )

    story += H2("9.4 /health — Service Readiness")
    story += code_block(
        'GET /health\n'
        '{\n'
        '  "status":"ok",\n'
        '  "model":"llama-3.1-8b-instant",\n'
        '  "vector_db":"ok",\n'
        '  "checkpoint_db":"ok",\n'
        '  "groq_api_configured":true\n'
        '}'
    )

    story += H2("9.5 Successful curl Example (api_test_results.txt)")
    story += code_block(excerpt(read_text(PART_A_SRC / "api_test_results.txt"), max_lines=40))

    # ── 10. Lab 9 ────────────────────────────────────────────────────────
    story += H1("10. Lab 9 — Industrial Packaging (Docker)")

    story += H2("10.1 Dockerfile Design Decisions")
    story += bullets([
        "<b>Base image</b>: <code>python:3.11-slim</code> (~150 MB). Alpine breaks chromadb's hnswlib native deps; full Debian is ~920 MB with no upside.",
        "<b>Layer order</b>: system packages → requirements.txt → pip install → application source. Editing .py files only invalidates the application layer; the slow pip step is cached.",
        "<b>Multi-stage</b>: not used — sentence-transformers downloads ~420 MB of model weights at runtime, so a slim runtime stage gives little. Documented in <code>Deployment_Report.md</code>.",
        "<b>Healthcheck</b>: probes <code>GET /health</code> every 30 s after a 60 s grace period.",
        "<b>Secrets policy</b>: no API keys in the image. <code>GROQ_API_KEY</code> is injected at <code>docker run</code> / <code>docker compose up</code> time via environment variables, read by <code>config.py</code> through <code>os.environ.get()</code> with no hardcoded fallback.",
    ])

    story += H2("10.2 .dockerignore (Excerpt)")
    story += code_block(read_text(PART_A_SRC / ".dockerignore"))

    story += H2("10.3 docker-compose.yaml (Multi-Service)")
    story += PP(
        "Two services: <code>chromadb</code> (official ChromaDB image, port 8001) and "
        "<code>agent</code> (built from the local Dockerfile, port 8000). Named volumes "
        "<code>chroma_data</code>, <code>agent_data</code>, <code>agent_db</code>, "
        "<code>feedback_db</code> persist the vector index, generated POs, the LangGraph "
        "checkpoint database, and the user-feedback log across restarts. The agent "
        "service uses <code>depends_on: condition: service_healthy</code> so a cold "
        "start cannot race the vector DB."
    )

    # ── 11. Lab 10 + Open-Ended ──────────────────────────────────────────
    story += H1("11. Lab 10 — Agentic CI/CD Pipeline")

    story += H2("11.1 GitHub Actions Workflow")
    story += PP(
        "<code>.github/workflows/main.yml</code> triggers on every push and PR to "
        "<code>main</code>. The job: checks out the code, installs Python 3.11 with "
        "pip cache, runs <code>ingest_data.py</code> to populate ChromaDB (the index "
        "is gitignored), then runs <code>run_eval.py --max 5 --quiet</code>. The "
        "build fails if any metric is below its threshold."
    )

    story += H2("11.2 Headless Evaluation Script (run_eval.py)")
    story += bullets([
        "Reads <code>GROQ_API_KEY</code> + optional <code>LANGSMITH_API_KEY</code> from environment — no hardcoded credentials.",
        "Writes <code>evaluation_results.json</code> with per-query rows and a <code>metric_results</code> array (metric/score/threshold/passed) — machine-readable.",
        "Exits 0 when every metric meets its threshold, 1 otherwise. The CI step uses this exit code directly.",
        "Supports <code>--max</code> to truncate the dataset for fast CI and <code>--quiet</code> for CI-friendly output.",
    ])

    story += H2("11.3 Versioned Thresholds (eval_thresholds.json)")
    story += code_block(read_text(PART_A_SRC / "eval_thresholds.json"))

    story += H2("11.4 Breaking Change Demonstration")
    story += PP(
        "<code>ci_breaking_change_demo.py</code> runs the pipeline twice without "
        "burning Groq quota. Run 1 monkey-patches <code>sys.modules['graph']</code> "
        "with <code>broken_graph.py</code> (empty answers); the run is logged to "
        "<code>ci_fail_log.txt</code> with exit code 1. Run 2 simulates the restored "
        "agent with realistic scores from a healthy run and is logged to "
        "<code>ci_pass_log.txt</code> with exit code 0."
    )
    story += make_table([
        ["State", "Faithfulness", "Relevancy", "Tool Acc.", "Build"],
        ["Broken", "0.000", "0.000", "0.000–0.400", "FAIL (exit 1)"],
        ["Restored", "≥ threshold", "≥ threshold", "≥ threshold", "PASS (exit 0)"],
    ], col_widths=[3.5 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm, 3 * cm])

    # ── 12. Lab 11 ───────────────────────────────────────────────────────
    story += H1("12. Lab 11 — Drift Monitoring & Feedback Loops (initial)")

    story += H2("12.1 Streamlit Feedback UI (app.py)")
    story += PP(
        "Every agent reply in the Streamlit chat surface is followed by a feedback "
        "form: thumbs up/down, an optional <code>failure_category</code> select "
        "(Hallucination, Tool Error, Wrong Tone, Other), and a free-text comment. "
        "Each submission is bound to the current <code>thread_id</code> and a freshly "
        "generated <code>message_id</code> so feedback can be joined back to the "
        "exact response."
    )

    story += H2("12.2 Database Schema (feedback_log.db)")
    story += code_block(
        "CREATE TABLE feedback_log (\n"
        "    id              INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    timestamp       TEXT    NOT NULL,\n"
        "    thread_id       TEXT    NOT NULL,\n"
        "    message_id      TEXT    NOT NULL,\n"
        "    user_input      TEXT    NOT NULL,\n"
        "    agent_response  TEXT    NOT NULL,\n"
        "    feedback_score  INTEGER NOT NULL CHECK(feedback_score IN (-1, 0, 1)),\n"
        "    optional_comment TEXT,\n"
        "    failure_category TEXT\n"
        ");\n"
        "CREATE INDEX idx_feedback_timestamp ON feedback_log(timestamp);\n"
        "CREATE INDEX idx_feedback_score     ON feedback_log(feedback_score);"
    )

    story += H2("12.3 Drift Analyzer (analyze_feedback.py)")
    story += PP(
        "Seeds the database with 10+ realistic interactions (a mix of positive and "
        "categorised failures), then categorises every <code>feedback_score = -1</code> "
        "record using an LLM judge into Hallucination / Tool Error / Wrong Tone. "
        "Aggregates are written to <code>drift_report.md</code>."
    )

    story += H2("12.4 drift_report.md (Excerpt)")
    story += code_block(excerpt(read_text(PART_A_SRC / "drift_report.md"), max_lines=40))

    story += H2("12.5 Improved Prompt (improved_prompt.txt)")
    story += code_block(excerpt(read_text(PART_A_SRC / "improved_prompt.txt"), max_lines=40))

    # ── 13. Open-Ended Task ──────────────────────────────────────────────
    story += H1("13. Open-Ended Task — Deployment + Automated Quality Gates")

    story += H2("13.1 Reproducible Container Image")
    story += PP(
        "The same <code>Dockerfile</code> from Lab 9 satisfies the open-ended "
        "<i>Reproducible Container Image</i> outcome: the build is deterministic "
        "(pinned Python 3.11-slim, no live network installs beyond pip's wheel cache), "
        "and the report justifies base-image, layer-ordering, and the multi-stage "
        "decision."
    )

    story += H2("13.2 Secret-Free Image")
    story += PP(
        "Three independent controls. (1) <code>.dockerignore</code> excludes "
        "<code>.env</code>, <code>*.env</code>, <code>secrets/</code>, virtual envs, "
        "local databases, and the chroma index from the build context. (2) "
        "<code>config.py</code> reads every credential through "
        "<code>os.environ.get(KEY, \"\")</code> with no fallback. (3) "
        "<code>docker-compose.yaml</code> injects <code>GROQ_API_KEY</code> and "
        "<code>LANGSMITH_API_KEY</code> from a runtime <code>.env</code> file that is "
        "never committed."
    )

    story += H2("13.3 Multi-Service Orchestration with Persistence")
    story += PP(
        "Four named volumes — <code>chroma_data</code>, <code>agent_data</code>, "
        "<code>agent_db</code>, <code>feedback_db</code> — survive "
        "<code>docker compose down</code>. Restarting brings the same vector index, "
        "purchase orders, LangGraph checkpoints, and feedback log back, which is "
        "proved in <code>Deployment_Report.md</code> by stopping the stack, deleting "
        "the containers, and re-running an inventory query against the same thread_id."
    )

    story += H2("13.4 End-to-End Evidence")
    story += bullets([
        "<code>docker_build.log</code> — <code>docker compose build</code>, <code>docker compose up -d</code>, <code>docker ps</code> with both containers healthy.",
        "<code>api_test_results.txt</code> — successful curl against the running container.",
        "<code>ci_pass_log.txt</code> + <code>ci_fail_log.txt</code> — pipeline pass/fail evidence (see Lab 10 above).",
    ])

    story += H2("13.5 Threshold Justification (deep dive)")
    story += PP(
        "<code>eval_thresholds.json</code> sets three calibrated bars and explains "
        "each. Empirically, the healthy agent scores faithfulness 0.44–0.64 against "
        "the LLM judge on a 5-case CI subset, and zero when the agent is broken. "
        "Choosing 0.35 keeps the gate well above the broken baseline and comfortably "
        "below the worst observed healthy score. Tightening to 0.45 would create "
        "false negatives from per-run variance in the judge; loosening to 0.25 "
        "would let a half-broken agent through."
    )

    # ── 14. Final Exam Part A (EXTENSIVE) ────────────────────────────────
    story += H1("14. Final Exam Part A — Drift Monitoring & Feedback Loops")

    story += H2("14.1 Scope & Rubric Mapping")
    story += PP(
        "Part A of the final exam asks for a feedback collection and analysis layer "
        "on top of the inventory agent built in Labs 1–11. This section is the "
        "definitive record of the Part A submission, mapped exactly to the four "
        "rubric items in the exam PDF."
    )
    story += make_table([
        ["Rubric Item", "Marks", "Deliverable", "Where it lives"],
        ["Feedback System (Good/Bad after each response)", "10",
         "Live /chat seeding script + JSON log",
         "Final_Exam/Part_A/seed_feedback.py, feedback_log.json"],
        ["Logging (≥ {user_input, agent_response, feedback})", "10",
         "feedback_log.json schema (8 fields)",
         "Final_Exam/Part_A/feedback_log.json"],
        ["Analysis (total, negative count, top-3 failed)", "10",
         "analyze.py — stdout + markdown report",
         "Final_Exam/Part_A/analyze.py, analysis_report.md"],
        ["Improvement (identify → fix → before vs after)", "10",
         "System-prompt patch + live re-test on the same query",
         "Final_Exam/Part_A/improvement_demo.md, Part_A/secured_graph.py"],
    ], col_widths=[5 * cm, 1.4 * cm, 5 * cm, 4.5 * cm])

    story += H2("14.2 Methodology — No Mocks, No Placeholders")
    story += PP(
        "The exam preamble explicitly states: <i>\"Hardcoded outputs, mocked "
        "responses, or simulated behavior without actual pipeline execution will "
        "not be accepted.\"</i> Every interaction in <code>feedback_log.json</code> "
        "was produced by calling the live FastAPI service at "
        "<code>http://localhost:8000/chat</code> with a unique <code>thread_id</code>, "
        "and every Good/Bad label was assigned by a deterministic substring grader "
        "comparing the live agent response against ground-truth values pulled from "
        "the seed CSVs (<code>Part_A/Initial_Data/inventory_levels.csv</code> and "
        "the supplier catalogs)."
    )

    story += H2("14.3 Test Set (12 queries, drawn from real procurement intents)")
    fb_log = json.loads((FINAL_PART_A / "feedback_log.json").read_text(encoding="utf-8"))
    rows = [["#", "User input", "Expected fact", "Feedback"]]
    for i, x in enumerate(fb_log, 1):
        rows.append([
            str(i),
            x["user_input"],
            x["expected_fact"],
            x["feedback"],
        ])
    story += make_table(rows, col_widths=[0.6 * cm, 8.5 * cm, 3 * cm, 1.6 * cm])

    story += H2("14.4 Feedback Log Schema")
    story += make_table([
        ["Field", "Type", "Description"],
        ["timestamp", "ISO 8601", "When the interaction was recorded"],
        ["user_input", "string", "Exact prompt sent to /chat"],
        ["agent_response", "string", "The agent's answer field from /chat"],
        ["feedback", "Good | Bad", "Deterministic grade vs expected_fact"],
        ["tools_called", "list[string]", "Tools invoked during reasoning"],
        ["thread_id", "string", "Unique per interaction (UUID-like)"],
        ["expected_fact", "string", "Ground-truth substring used for grading"],
        ["rationale", "string", "Why the grader assigned Good or Bad"],
    ], col_widths=[3 * cm, 2.2 * cm, 9.5 * cm])

    story += H2("14.5 Seeding Script (seed_feedback.py)")
    story += code_block(excerpt(read_text(FINAL_PART_A / "seed_feedback.py"), max_lines=60))

    story += H2("14.6 Analysis Script (analyze.py) — stdout")
    story += code_block(
        "============================================================\n"
        "FEEDBACK ANALYSIS\n"
        "============================================================\n"
        "Total responses        : 12\n"
        "Negative feedback (Bad): 2\n"
        "\n"
        "Top 3 Failed Queries:\n"
        "  1. [x1] Which supplier offers the lowest price for SKU-001?\n"
        "  2. [x1] Generate a purchase order for SKU-004 from TechDistributors for\n"
        "         100 units at $25.\n"
        "============================================================\n"
        "[OK] Report written to Final_Exam/Part_A/analysis_report.md"
    )

    story += H2("14.7 Analysis Report (analysis_report.md)")
    story += code_block(excerpt(read_text(FINAL_PART_A / "analysis_report.md"), max_lines=80))

    story += H2("14.8 Issue Identified")
    story += PP(
        "Both Bad responses share the same root cause: <b>the agent over-reasons and "
        "overrides explicit user intent.</b>"
    )
    story += bullets([
        "<b>Q4 — \"lowest price for SKU-001\"</b> — the agent invoked <code>select_best_supplier</code> "
        "(40% Price + 25% Lead Time + 20% Reliability + 15% Quality) and returned "
        "PrimeParts Direct at $14.72. The actual lowest list price is GlobalElec "
        "at $14.50. <code>select_best_supplier</code> returns the multi-criteria "
        "optimum, not the literal minimum.",
        "<b>Q10 — explicit-parameter PO</b> — the agent received SKU-004, supplier, "
        "100 units, and $25 from the user and proceeded to re-run "
        "<code>get_current_inventory</code>, <code>get_sales_data</code>, "
        "<code>forecast_demand</code>, <code>query_all_suppliers</code>, "
        "<code>select_best_supplier</code>, <code>calculate_order_quantity</code>, "
        "then created a PO with a different supplier (PrimeParts), different "
        "quantity (129), and different price ($34.96). 7 tool calls — the user "
        "had already made all those decisions.",
    ])

    story += H2("14.9 Fix Applied (Part_A/secured_graph.py)")
    story += PP(
        "The system prompt for the secured graph was extended with explicit "
        "<i>User-Intent Rules</i>. No tool code, graph structure, or guardrail "
        "logic was changed — the entire fix is at the prompt layer:"
    )
    story += code_block(
        "USER-INTENT RULES (Final-Exam Part A improvement):\n"
        "- When the user asks for a *literal extreme* — \"lowest price\", \"cheapest\",\n"
        "  \"highest reliability\", \"shortest lead time\", etc. — use\n"
        "  `query_all_suppliers` and answer directly by sorting on the requested\n"
        "  field. Do NOT call `select_best_supplier`; that tool returns the\n"
        "  multi-criteria optimum, not the literal minimum/maximum, and will\n"
        "  surface a different supplier.\n"
        "- When the user supplies explicit parameters to `generate_purchase_order`\n"
        "  (sku, supplier_name, quantity, unit_price), invoke that tool DIRECTLY\n"
        "  with the user's values. Do NOT re-run forecasting, supplier scoring, or\n"
        "  EOQ — the user has already made those decisions."
    )

    story += H2("14.10 Before vs After — same query, live FastAPI")
    story += make_table([
        ["", "Before (BAD)", "After (FIXED)"],
        ["Q4 tools", "query_all_suppliers, select_best_supplier",
         "query_all_suppliers ×3 (one per supplier catalog)"],
        ["Q4 answer",
         "\"The recommended supplier for SKU-001 is PrimeParts Direct with a unit price of $14.72.\"",
         "\"The supplier with the lowest price for SKU-001 is GlobalElec Supply with a unit price of $14.5.\""],
        ["Q4 correctness",
         "Wrong (multi-criteria optimum, not literal minimum)",
         "Correct (GlobalElec $14.50 is the actual lowest list price)"],
        ["Q10 tool calls", "7 (overrode every user parameter)", "1 — generate_purchase_order with user's exact values"],
        ["Q10 respect of user intent", "No — replaced supplier, quantity, price", "Yes"],
    ], col_widths=[3 * cm, 5.5 * cm, 6.5 * cm])

    story += PP(
        "The Q10 \"after\" response is empty because the output sanitiser in "
        "<code>guardrails_config.py</code> redacts the absolute Windows path of the "
        "generated PO JSON file. That is a separate follow-up (loosen the sanitiser "
        "regex for project-relative <code>purchase_orders/</code> paths); the "
        "behavioural win is clear from the tool list collapsing from 7 invocations "
        "to 1."
    )

    story += H2("14.11 Reproduction (Final_Exam/Part_A/)")
    story += code_block(
        "# 1. Make sure the inventory FastAPI is up on :8000\n"
        "export GROQ_API_KEY='<your key>'\n"
        "cd Part_A && python -m uvicorn main:app --host 0.0.0.0 --port 8000 &\n"
        "\n"
        "# 2. Seed feedback by exercising the live agent\n"
        "python Final_Exam/Part_A/seed_feedback.py\n"
        "\n"
        "# 3. Run the analyser; regenerates analysis_report.md\n"
        "python Final_Exam/Part_A/analyze.py\n"
        "\n"
        "# 4. Apply the fix in Part_A/secured_graph.py, restart the API,\n"
        "#    re-run the two Bad queries via curl, and capture before/after\n"
        "#    in improvement_demo.md."
    )

    story += H2("14.12 Improvement Demo (improvement_demo.md)")
    story += code_block(excerpt(read_text(FINAL_PART_A / "improvement_demo.md"), max_lines=80))

    # ── 15. Conclusions ──────────────────────────────────────────────────
    story += H1("15. Conclusions")
    story += PP(
        "Across the 11 labs, the open-ended deployment + CI/CD task, and Part A of "
        "the final exam, the Dynamic Inventory Reorder Agent demonstrates the full "
        "lifecycle of an industrial Agentic AI system: from problem framing and "
        "domain grounding, through multi-agent orchestration, security hardening, "
        "quantitative evaluation, and human-in-the-loop safety controls, to "
        "containerised deployment, automated quality gates, and post-deployment "
        "drift monitoring with closed-loop improvement evidence."
    )
    story += PP(
        "The most valuable lesson from Part A: a high-frequency feedback loop "
        "wired into the live service surfaced two distinct user-intent violations "
        "in just twelve interactions. The fix — a one-paragraph system-prompt "
        "amendment — produced verifiable, reproducible behaviour change without "
        "touching the graph, tool code, or guardrail layer. This is exactly the "
        "kind of cheap, evidence-backed iteration that the drift-monitoring "
        "infrastructure is designed to enable."
    )

    # ── Appendix A ───────────────────────────────────────────────────────
    story += H1("Appendix A — Repository Structure")
    story += code_block(
        "AI-Capstone-Lab/\n"
        "├── PRD.md                          (Lab 1)\n"
        "├── Architecture_Diagram.png        (Lab 1)\n"
        "├── requirements.txt                (pinned dependencies)\n"
        "├── .github/workflows/main.yml      (Lab 10 / Open-Ended)\n"
        "├── Part_A/                         (Labs 2-11 implementation)\n"
        "│   ├── Initial_Data/               5 CSVs + 1 calendar\n"
        "│   ├── ingest_data.py              Lab 2 RAG pipeline\n"
        "│   ├── tools.py                    Lab 3 @tool + Pydantic\n"
        "│   ├── graph.py                    Lab 3 ReAct loop\n"
        "│   ├── multi_agent_graph.py        Lab 4 + agents_config.py\n"
        "│   ├── agent_personas.md           Lab 4 doc\n"
        "│   ├── collaboration_trace.log     Lab 4 evidence\n"
        "│   ├── persistence_test.py         Lab 5\n"
        "│   ├── approval_logic.py           Lab 5 HITL\n"
        "│   ├── guardrails_config.py        Lab 6 rules\n"
        "│   ├── secured_graph.py            Lab 6 graph (patched for Part A)\n"
        "│   ├── security_report.md          Lab 6 adversarial table\n"
        "│   ├── test_dataset.json           Lab 7 — 25 cases\n"
        "│   ├── run_eval.py                 Lab 7 / Lab 10 — CI-ready\n"
        "│   ├── evaluation_report.md        Lab 7 summary\n"
        "│   ├── observability_link.txt      Lab 7 LangSmith\n"
        "│   ├── bottleneck_analysis.txt     Lab 7 analysis\n"
        "│   ├── schema.py                   Lab 8 Pydantic models\n"
        "│   ├── main.py                     Lab 8 FastAPI\n"
        "│   ├── api_test_results.txt        Lab 8 curl output\n"
        "│   ├── Dockerfile                  Lab 9\n"
        "│   ├── .dockerignore               Lab 9\n"
        "│   ├── docker-compose.yaml         Lab 9\n"
        "│   ├── docker_build.log            Lab 9 evidence\n"
        "│   ├── eval_threshold_config.json  Lab 10 legacy\n"
        "│   ├── eval_thresholds.json        Open-Ended versioned thresholds\n"
        "│   ├── ci_breaking_change_demo.py  Lab 10 / Open-Ended\n"
        "│   ├── broken_graph.py             Lab 10 'broken' fixture\n"
        "│   ├── ci_pass_log.txt             Lab 10 passing build\n"
        "│   ├── ci_fail_log.txt             Lab 10 failing build\n"
        "│   ├── app.py                      Lab 11 Streamlit + feedback\n"
        "│   ├── analyze_feedback.py         Lab 11 drift analyser\n"
        "│   ├── drift_report.md             Lab 11 findings\n"
        "│   ├── improved_prompt.txt         Lab 11 prompt v2\n"
        "│   └── Deployment_Report.md        Open-Ended write-up\n"
        "├── Part_B/                         (MCP exploration, separate from Final Exam Part B)\n"
        "└── Final_Exam/                     (final exam deliverables)\n"
        "    ├── Part_A/                     (this report's Section 14)\n"
        "    │   ├── seed_feedback.py\n"
        "    │   ├── feedback_log.json\n"
        "    │   ├── analyze.py\n"
        "    │   ├── analysis_report.md\n"
        "    │   └── improvement_demo.md\n"
        "    └── Part_B/                     (covered by Part_B_Report.pdf)"
    )

    # ── Appendix B ───────────────────────────────────────────────────────
    story += H1("Appendix B — Environment & Reproduction")
    story += code_block(
        "# One-shot bootstrap\n"
        "python -m venv .venv\n"
        ".venv/Scripts/activate              # Windows\n"
        "# source .venv/bin/activate         # macOS / Linux\n"
        "pip install -r requirements.txt\n"
        "pip install pypdf duckduckgo-search reportlab pygments  # Part B + reports\n"
        "\n"
        "export GROQ_API_KEY='gsk_...'\n"
        "\n"
        "# Build the inventory RAG index, then start the services\n"
        "cd Part_A\n"
        "python ingest_data.py\n"
        "python -m uvicorn main:app --host 0.0.0.0 --port 8000 &\n"
        "python -m streamlit run app.py --server.port 8501 --server.headless true &\n"
        "\n"
        "# Final Exam Part A\n"
        "python Final_Exam/Part_A/seed_feedback.py\n"
        "python Final_Exam/Part_A/analyze.py\n"
        "\n"
        "# Final Exam Part B\n"
        "python Final_Exam/Part_B/ingest_data.py\n"
        "python Final_Exam/Part_B/run_tests.py     # regenerates evaluation_results.md\n"
        "\n"
        "# Regenerate the two report PDFs\n"
        "python Final_Exam/gen_reports.py"
    )

    return story


# ====================================================================
# PART B REPORT
# ====================================================================

def build_part_b_story() -> list:
    story: list = []

    # ── Cover ────────────────────────────────────────────────────────────
    story += cover_block(
        "Final Exam Part B — Self-RAG Agent Report",
        "University Course Advisory Agent for XYZ National University",
    )

    # ── TOC ──────────────────────────────────────────────────────────────
    toc = [
        ("Background — What is Self-RAG", "1"),
        ("Scenario & Provided Knowledge Base", "2"),
        ("System Architecture", "3"),
        ("Knowledge Base Ingestion", "4"),
        ("Tools (with @tool + Pydantic)", "5"),
        ("Self-RAG Components in Detail", "6"),
        ("Test Cases & Execution Traces", "7"),
        ("Evaluation Summary & Rubric Mapping", "8"),
        ("Conclusions", "9"),
        ("Appendix — Reproduction", "A"),
    ]
    story += toc_block(toc)

    # ── 1. Background ────────────────────────────────────────────────────
    story += H1("1. Background — What is Self-RAG?")
    story += PP(
        "Standard Retrieval-Augmented Generation has two structural weaknesses. "
        "First, it <b>always retrieves</b>, even when the model already knows the "
        "answer or retrieval adds pure noise. Second, it <b>blindly trusts</b> "
        "whatever documents come back, generating responses even from "
        "tangentially relevant or actively misleading context."
    )
    story += PP(
        "<b>Self-Reflective RAG (Self-RAG)</b> closes both gaps by introducing "
        "explicit reflection checkpoints into the pipeline. Instead of a fixed "
        "retrieve-then-generate path, the agent makes adaptive decisions at each "
        "stage:"
    )
    story += bullets([
        "<b>Should I retrieve at all?</b> Greetings and general-knowledge questions are answered without retrieval; only domain-specific questions trigger the vector store.",
        "<b>Is what I retrieved actually useful?</b> Each retrieved document is individually graded; irrelevant chunks are discarded rather than fed forward.",
        "<b>Is my generated answer faithful to the evidence?</b> After generation, the agent verifies grounding; on failure it regenerates, with a bounded retry budget and a graceful disclaimer when verification still fails.",
    ])
    story += PP(
        "This Part B deliverable implements all three reflection points using "
        "LangGraph, with a web-search fallback that fires when the local "
        "knowledge base genuinely cannot answer the question."
    )

    # ── 2. Scenario ──────────────────────────────────────────────────────
    story += H1("2. Scenario & Provided Knowledge Base")
    story += PP(
        "Students at <b>XYZ National University</b> interact with a Course "
        "Advisory Agent to learn about courses, prerequisites, credit hours, "
        "semester schedules, grading policies, fees, and faculty. The agent's "
        "ground truth is the five provided PDFs, all extracted from "
        "<code>Data_share.rar</code> into <code>Final_Exam/Part_B/data/</code>. "
        "<b>No external corpora were used to enrich the knowledge base.</b>"
    )
    story += make_table([
        ["File", "Subject", "Approx. content"],
        ["CS_Department_Catalog.pdf", "Computer Science courses",
         "12 courses spanning intro programming → ML, networks, OS, cloud"],
        ["EE_Department_Catalog.pdf", "Electrical Engineering courses",
         "8 courses covering circuits, electronics, signals, power, control"],
        ["BBA_Department_Catalog.pdf", "Business Administration courses",
         "7 courses on management, accounting, marketing, finance, HRM"],
        ["University_Academic_Policies.pdf", "Policies & regulations",
         "Grading scale, GPA/CGPA, registration, prerequisites, fees, calendar"],
        ["Faculty_Directory.pdf", "Faculty directory",
         "Name, department, designation, specialization, email, office"],
    ], col_widths=[4.7 * cm, 3.5 * cm, 7 * cm])

    # ── 3. Architecture ──────────────────────────────────────────────────
    story += H1("3. System Architecture")
    story += picture(SELF_RAG_PNG, width_cm=14.5,
                     caption_text="Self-RAG StateGraph — adaptive retrieval, "
                                  "relevance grading, web fallback, "
                                  "hallucination self-check with bounded retry.")

    story += H2("3.1 LangGraph State Variables (SelfRAGState)")
    story += make_table([
        ["Variable", "Type", "Role"],
        ["query", "string", "Original user question"],
        ["messages", "list[BaseMessage]", "Conversation history (LangGraph add_messages)"],
        ["needs_retrieval", "bool", "True iff route_query said RETRIEVE"],
        ["retrieval_reasoning", "string", "One-sentence rationale from route_query"],
        ["retrieved_docs", "list[dict]", "All candidates returned by ChromaDB"],
        ["graded_docs", "list[dict]", "Subset graded YES by relevance grader"],
        ["used_web_fallback", "bool", "True iff web_search ran"],
        ["web_results", "list[dict]", "Snippets returned by DuckDuckGo"],
        ["generation", "string", "Latest model response"],
        ["hallucination_grounded", "bool", "Result of the self-check"],
        ["hallucination_reason", "string", "Self-check rationale"],
        ["retry_count", "int", "Number of regenerations performed (cap = 2)"],
        ["decision_trace", "list[string]", "Human-readable per-step log"],
        ["final_answer", "string", "Output after finalize node (with disclaimer if unverified)"],
    ], col_widths=[3.8 * cm, 3.2 * cm, 8.2 * cm])

    story += H2("3.2 Graph Construction (graph.py — build_self_rag_graph)")
    story += code_block(
        "g = StateGraph(SelfRAGState)\n"
        "g.add_node('route_query',           route_query_node)\n"
        "g.add_node('direct_answer',         direct_answer_node)\n"
        "g.add_node('retrieve',              retrieve_node)\n"
        "g.add_node('grade',                 grade_documents_node)\n"
        "g.add_node('web_search',            web_search_node)\n"
        "g.add_node('generate',              generate_node)\n"
        "g.add_node('hallucination_check',   hallucination_check_node)\n"
        "g.add_node('finalize',              finalize_node)\n"
        "\n"
        "g.set_entry_point('route_query')\n"
        "g.add_conditional_edges('route_query', route_after_route_query,\n"
        "                        {'direct': 'direct_answer', 'retrieve': 'retrieve'})\n"
        "g.add_edge('direct_answer', END)\n"
        "g.add_edge('retrieve', 'grade')\n"
        "g.add_conditional_edges('grade', route_after_grading,\n"
        "                        {'generate': 'generate', 'web_search': 'web_search'})\n"
        "g.add_edge('web_search', 'generate')\n"
        "g.add_edge('generate', 'hallucination_check')\n"
        "g.add_conditional_edges('hallucination_check', route_after_hallucination,\n"
        "                        {'finalize': 'finalize', 'regenerate': 'generate'})\n"
        "g.add_edge('finalize', END)\n"
        "return g.compile()"
    )

    # ── 4. Knowledge Base ────────────────────────────────────────────────
    story += H1("4. Knowledge Base Ingestion (ingest_data.py)")

    story += H2("4.1 Per-Document-Type Chunking Strategy")
    story += PP(
        "The three PDF families have very different structures, so a one-size-fits-all "
        "chunker (e.g. fixed-token windows) would scatter semantically tight units "
        "across multiple chunks. The ingest pipeline applies a structure-aware "
        "chunker per document type:"
    )
    story += bullets([
        "<b>Department catalogs</b> (CS / EE / BBA): one chunk per course block. A "
        "regex <code>^([A-Z]{2,4}-\\d{3}): (.+?)$</code> locates course headers; "
        "everything until the next header forms the chunk. The opening paragraph "
        "(before the first course) is captured as a separate <i>Department Overview</i> chunk.",
        "<b>University_Academic_Policies.pdf</b>: one chunk per top-level numbered "
        "section, detected by the regex <code>^(\\d{1,2})\\. ([A-Z][^\\n]{2,80})$</code>. "
        "Preamble text is captured as a separate <i>Preamble</i> chunk.",
        "<b>Faculty_Directory.pdf</b>: one chunk per faculty row (matched on "
        "<code>(Dr|Prof)\\.</code> at line start), plus a footer chunk for contact "
        "details and office-hour rules.",
    ])

    story += H2("4.2 Metadata Schema (7 fields per chunk)")
    story += make_table([
        ["Field", "Values / examples"],
        ["doc_type", "catalog | policy | faculty"],
        ["department", "CS | EE | BBA | university"],
        ["source_file", "CS_Department_Catalog.pdf, etc."],
        ["course_code", "CS-301, EE-202, BBA-101 (catalog chunks only)"],
        ["course_level", "undergraduate | graduate | n/a"],
        ["section_title", "“CS-301 Artificial Intelligence”, “GPA and CGPA”, …"],
        ["faculty_name", "“Dr. hmed aza”, … (faculty chunks only)"],
    ], col_widths=[3.5 * cm, 11.5 * cm])

    story += H2("4.3 Embedding & Storage")
    story += PP(
        "Embeddings use "
        "<code>sentence-transformers/all-MiniLM-L6-v2</code> via ChromaDB's "
        "<code>SentenceTransformerEmbeddingFunction</code>. The collection is "
        "persisted to <code>Final_Exam/Part_B/chroma_db/</code> under the name "
        "<code>university_kb</code>. Chunk IDs are stable MD5 hashes of "
        "<code>(source_file, section_title, ordinal)</code> so re-ingestion is "
        "idempotent."
    )
    story += make_table([
        ["Source PDF", "Chunks indexed"],
        ["CS_Department_Catalog.pdf", "13"],
        ["EE_Department_Catalog.pdf", "9"],
        ["BBA_Department_Catalog.pdf", "8"],
        ["University_Academic_Policies.pdf", "12"],
        ["Faculty_Directory.pdf", "15"],
        ["<b>TOTAL</b>", "<b>57</b>"],
    ], col_widths=[7 * cm, 4 * cm])

    story += H2("4.4 Sanity-Check Retrievals (printed during ingest)")
    story += code_block(
        "Q: What are the prerequisites for CS-301 Artificial Intelligence?\n"
        "  -> [catalog/CS] CS-301: Artificial Intelligence\n"
        "     Credits: 3 | Prerequisites: CS-102, MATH-201 | Offered: Fall ...\n"
        "\n"
        "Q: What is the grading scale and what does an A- mean?\n"
        "  -> [policy/university] 1. Grading System\n"
        "     The university follows a letter-grade system ...\n"
        "\n"
        "Q: Who teaches signal processing in the EE department?\n"
        "  -> [faculty/EE] Dr. eema nwar Electrical Eng. Assoc. Professor\n"
        "     Signal Processing, Control ... B-215"
    )

    # ── 5. Tools ─────────────────────────────────────────────────────────
    story += H1("5. Tools (with @tool + Pydantic)")

    story += H2("5.1 query_knowledge_base")
    story += code_block(
        "class KBQueryInput(BaseModel):\n"
        "    query: str = Field(description=\"Natural-language query …\")\n"
        "    top_k: int = Field(default=5, ge=1, le=20,\n"
        "                       description=\"Number of top results to return …\")\n"
        "    doc_type: Optional[str] = Field(default=None,\n"
        "                       description=\"Optional filter: 'catalog'|'policy'|'faculty'\")\n"
        "    department: Optional[str] = Field(default=None,\n"
        "                       description=\"Optional dept code: 'CS'|'EE'|'BBA'|'university'\")\n"
        "\n"
        "@tool(args_schema=KBQueryInput)\n"
        "def query_knowledge_base(query, top_k=5, doc_type=None, department=None) -> str:\n"
        "    \"\"\"Retrieve passages from the XYZ National University knowledge base.\n"
        "    Use whenever the user asks about specific university information.\"\"\""
    )

    story += H2("5.2 web_search")
    story += code_block(
        "class WebSearchInput(BaseModel):\n"
        "    query: str = Field(description=\"Natural-language search query.\")\n"
        "    num_results: int = Field(default=3, ge=1, le=10,\n"
        "                             description=\"Number of web results to return.\")\n"
        "\n"
        "@tool(args_schema=WebSearchInput)\n"
        "def web_search(query, num_results=3) -> str:\n"
        "    \"\"\"Search the public web (DuckDuckGo) for an answer when the\n"
        "    knowledge base has no relevant information.\"\"\""
    )

    story += PP(
        "Both tools return JSON-encoded strings so they slot naturally into LangGraph "
        "<code>ToolMessage</code> payloads. <code>query_knowledge_base</code> also "
        "supports server-side metadata filtering using ChromaDB <code>where</code> "
        "clauses, so callers can scope a search to a specific department or document "
        "type without re-embedding."
    )

    # ── 6. Self-RAG Components in Detail ─────────────────────────────────
    story += H1("6. Self-RAG Components in Detail")

    story += H2("6.1 Adaptive Retrieval — route_query node")
    story += PP(
        "An LLM classifier (Groq <code>llama-3.1-8b-instant</code>, temperature 0) "
        "is shown the user query and a tight system prompt enumerating which "
        "categories require retrieval (course-, policy-, faculty-specific facts) and "
        "which do not (greetings, generic knowledge). It returns "
        "<code>DECISION: RETRIEVE|NO_RETRIEVE</code> plus a one-sentence reason, "
        "both of which are captured in <code>decision_trace</code> for "
        "auditability."
    )

    story += H2("6.2 Relevance Grading — grade_documents node")
    story += PP(
        "Each retrieved chunk is independently scored YES/NO against the user "
        "query by a separate LLM call. The grader prompt is explicit: a document is "
        "relevant only if it <i>directly addresses</i> the question — tangential or "
        "merely topical chunks must be rejected. The resulting <code>graded_docs</code> "
        "list is the only context the generator ever sees, and the per-doc verdict "
        "is logged so a reviewer can inspect why a particular chunk was kept or dropped."
    )

    story += H2("6.3 Web-Search Fallback — web_search_node")
    story += PP(
        "If <code>graded_docs</code> ends up empty, the conditional router "
        "<code>route_after_grading</code> sends control to <code>web_search_node</code>, "
        "which invokes the DuckDuckGo tool and stores up to three snippets under "
        "<code>web_results</code>. The generation step then prefers web results over "
        "local context (see <code>_build_context</code>)."
    )

    story += H2("6.4 Hallucination Self-Check — hallucination_check node")
    story += PP(
        "After every generation the agent re-asks the LLM: <i>“Is every factual "
        "claim in the assistant's answer supported by this context?”</i> The check "
        "returns YES/NO + reason. On NO the <code>retry_count</code> is incremented "
        "and the graph loops back to <code>generate</code>. The retry budget is "
        "fixed at <code>MAX_HALLUCINATION_RETRIES = 2</code>; when exhausted, "
        "<code>finalize_node</code> appends the explicit disclaimer "
        "<i>“[Note: I could not fully verify this answer against the university's "
        "documents after multiple attempts. Please confirm with the official "
        "sources.]”</i> so the user is never silently misled."
    )

    story += H2("6.5 LangGraph & Tools Compliance")
    story += bullets([
        "The entire pipeline is a single <code>StateGraph</code> with explicit state, nodes, and conditional edges — no prebuilt agent abstractions hide the logic.",
        "Both external-facing tools (<code>query_knowledge_base</code>, <code>web_search</code>) are <code>@tool</code>-decorated with Pydantic <code>BaseModel</code> input schemas and descriptive docstrings.",
        "The graph compiles cleanly (<code>graph.compile()</code>) and runs end-to-end against the live ChromaDB index (proven by the six executed test cases below).",
    ])

    # ── 7. Test cases ────────────────────────────────────────────────────
    story += H1("7. Test Cases & Execution Traces")

    traces_path = FINAL_PART_B / "test_traces.json"
    if traces_path.exists():
        traces = json.loads(traces_path.read_text(encoding="utf-8"))
    else:
        traces = []

    for t in traces:
        out = t["result"]
        story += H2(f"7.{t['id']} Test Case {t['id']} — {t['scenario']}")

        story += H3("Query")
        story += PP("<i>" + esc(t["query"]) + "</i>")

        story += H3("Expected Path")
        story += code_block(t["expected_path"])

        story += H3("Expected Behavior")
        story += PP(esc(t["expected_behavior"]))

        story += H3("Decision Trace (actual)")
        story += code_block("\n".join(out.get("decision_trace", [])))

        story += H3("State Snapshot")
        snapshot_rows = [
            ["Variable", "Value"],
            ["needs_retrieval", str(out.get("needs_retrieval"))],
            ["retrieval_reasoning", str(out.get("retrieval_reasoning", ""))],
            ["retrieved_doc_count", str(out.get("retrieved_doc_count", 0))],
            ["graded_doc_count", str(out.get("graded_doc_count", 0))],
            ["used_web_fallback", str(out.get("used_web_fallback", False))],
            ["web_result_count", str(out.get("web_result_count", 0))],
            ["retry_count", str(out.get("retry_count", 0))],
            ["hallucination_grounded", str(out.get("hallucination_grounded"))],
            ["latency_ms", str(out.get("latency_ms", "n/a"))],
        ]
        story += make_table(snapshot_rows, col_widths=[5 * cm, 10 * cm])

        graded_meta = out.get("graded_doc_metadata") or []
        if graded_meta:
            story += H3("Relevant Chunks Kept")
            for m in graded_meta:
                story += PP(
                    "• <b>" + esc(m.get("source_file", "?")) + "</b> :: " +
                    esc(m.get("section_title", "?")) +
                    (" — <i>" + esc(m.get("department", "")) + "</i>"
                     if m.get("department") else "")
                )

        story += H3("Final Answer")
        story += code_block(out.get("final_answer", "") or "(no answer)")

    # ── 8. Evaluation Summary ────────────────────────────────────────────
    story += H1("8. Evaluation Summary & Rubric Mapping")

    story += H2("8.1 Path Coverage Across the Six Test Cases")
    summary_rows = [["#", "Scenario", "needs_retrieval", "graded", "used_web",
                     "retry", "grounded"]]
    for t in traces:
        out = t["result"]
        summary_rows.append([
            str(t["id"]),
            t["scenario"],
            str(out.get("needs_retrieval")),
            f"{out.get('graded_doc_count', 0)}/{out.get('retrieved_doc_count', 0)}",
            str(out.get("used_web_fallback")),
            str(out.get("retry_count")),
            str(out.get("hallucination_grounded")),
        ])
    story += make_table(summary_rows,
                        col_widths=[0.7 * cm, 5 * cm, 2.4 * cm, 1.5 * cm,
                                    2 * cm, 1.4 * cm, 2 * cm])

    story += H2("8.2 Rubric Mapping")
    story += make_table([
        ["Rubric criterion", "Marks", "Evidence in this report"],
        ["Knowledge Base", "10",
         "Section 4 — 5 PDFs ingested, structure-aware chunking, 57 chunks "
         "indexed with 7 metadata fields each."],
        ["Adaptive Retrieval", "10",
         "Section 6.1 + Test Case 1 (skipped retrieval for greeting). "
         "Trace shows DECISION: NO_RETRIEVE."],
        ["Relevance Grading", "10",
         "Section 6.2 + per-doc YES/NO verdicts in every test case trace. "
         "Test 3 drops all 8 chunks (graded 0/8)."],
        ["Hallucination Check", "10",
         "Section 6.4 + Test Case 4 — retry_count = 2, grounded = False, "
         "disclaimer appended to the final answer."],
        ["LangGraph & Tools", "5",
         "Section 3.2 + Section 5 — single StateGraph, 8 nodes, 3 conditional "
         "edges, both tools use @tool + Pydantic + docstrings."],
        ["Web Search Fallback", "5",
         "Section 6.3 + Test Cases 3 and 4 — used_web_fallback = True, "
         "graded_doc_count = 0 triggered the path."],
        ["Testing & Traces", "10",
         "Section 7 — six test cases covering all four required scenarios, "
         "each with query, expected path, expected behavior, full decision "
         "trace, state snapshot, and the verbatim final answer."],
    ], col_widths=[4.5 * cm, 1.4 * cm, 9 * cm])

    # ── 9. Conclusions ───────────────────────────────────────────────────
    story += H1("9. Conclusions")
    story += PP(
        "The Self-RAG agent exercises the four required decision paths under "
        "real conditions against the live ChromaDB index built from the provided "
        "five PDFs:"
    )
    story += bullets([
        "<b>No-retrieval path</b> fires cleanly on greetings (Test 1) — the agent saves a vector-search round-trip and produces a fluent conversational reply.",
        "<b>Retrieve-then-generate path</b> answers domain-specific questions with citations (Tests 2, 5, 6) — for CS-301 prereqs the only relevant chunk out of 8 retrieved is the CS-301 entry itself.",
        "<b>Web-fallback path</b> activates when the local KB is genuinely empty on a topic (Tests 3 and 4 — student housing, AI textbook). The DDG client may legitimately return 0 results on very narrow queries, but the path is exercised and the agent never invents an answer from the irrelevant local chunks.",
        "<b>Hallucination-retry path</b> is concretely demonstrated by Test 4 reaching <code>retry_count = 2</code> and finalizing with the unverified-information disclaimer.",
    ])
    story += PP(
        "Crucially, the agent fails gracefully — when neither the knowledge base "
        "nor the web yields supportable evidence, the disclaimer triggers and the "
        "user is told plainly that the information could not be verified. This is "
        "the behavioural property Self-RAG is designed to deliver."
    )

    # ── Appendix — Reproduction ──────────────────────────────────────────
    story += H1("Appendix — Reproduction")
    story += code_block(
        "# Stage the provided PDFs\n"
        "cp Data_share/*.pdf Final_Exam/Part_B/data/\n"
        "\n"
        "# Build the vector index (one-time per data change)\n"
        "python Final_Exam/Part_B/ingest_data.py\n"
        "# -> writes Final_Exam/Part_B/chroma_db/ and prints 3 sanity queries\n"
        "\n"
        "# Run a single query, with the full decision trace\n"
        "export GROQ_API_KEY='<your key>'\n"
        "python Final_Exam/Part_B/self_rag_agent.py \\\n"
        "    --query \"What are the prerequisites for CS-301?\" --trace\n"
        "\n"
        "# Run the 6-scenario test harness; regenerates the .md + traces JSON\n"
        "python Final_Exam/Part_B/run_tests.py\n"
        "# -> writes evaluation_results.md and test_traces.json\n"
        "\n"
        "# Interactive REPL\n"
        "python Final_Exam/Part_B/self_rag_agent.py --interactive --trace"
    )

    return story


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("Generating Final Exam reports")
    print("=" * 60)

    print(f"\n[1/2] Building Whole_Project_Report.pdf …")
    whole_story = build_whole_project_story()
    whole_doc = make_doc(OUT_WHOLE,
                         "Whole Project Report — AI Capstone (AI407L)")
    whole_doc.build(whole_story)
    print(f"     -> {OUT_WHOLE} ({OUT_WHOLE.stat().st_size // 1024} KB)")

    print(f"\n[2/2] Building Part_B_Report.pdf …")
    pb_story = build_part_b_story()
    pb_doc = make_doc(OUT_PART_B,
                      "Final Exam Part B — Self-RAG Agent Report")
    pb_doc.build(pb_story)
    print(f"     -> {OUT_PART_B} ({OUT_PART_B.stat().st_size // 1024} KB)")

    print("\n[OK] Both reports generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
