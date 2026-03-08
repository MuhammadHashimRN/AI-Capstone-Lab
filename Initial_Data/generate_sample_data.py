"""
generate_sample_data.py — Creates all 5 sample data files in the Initial_Data/ folder.

Generates:
  1. supplier_catalog_techDistributors.pdf  — Supplier catalog with 10 SKUs
  2. inventory_policy.pdf                   — Reorder policies and safety stock formulas
  3. market_report_electronics_2024.pdf     — Demand trends and seasonal factors
  4. sales_history.csv                      — 12 months of daily sales for 5 SKUs
  5. supplier_performance.csv               — Supplier reliability data
"""

import csv
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent


def generate_supplier_catalog_pdf() -> None:
    """Create a realistic supplier catalog PDF with 10 SKUs, pricing tiers, MOQs, and lead times."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output_path = DATA_DIR / "supplier_catalog_techDistributors.pdf"
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"], fontSize=20, spaceAfter=20
    )
    elements.append(Paragraph("TechDistributors Inc — Product Catalog 2024", title_style))
    elements.append(Spacer(1, 0.3 * inch))

    # Company info
    elements.append(Paragraph(
        "Contact: orders@techdist.com | Phone: +1-555-0101 | Payment Terms: Net 30",
        styles["Normal"],
    ))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(
        "Minimum Order Value: $500 | Free Shipping on orders over $5,000",
        styles["Normal"],
    ))
    elements.append(Spacer(1, 0.4 * inch))

    # Product table
    catalog_items = [
        ["SKU", "Product Name", "Unit Price", "MOQ", "Bulk Price (100+)", "Lead Time (days)"],
        ["SKU-001", "Wireless Headphones Pro", "$15.00", "25", "$13.50", "7"],
        ["SKU-002", "USB-C Charging Cable 6ft", "$2.50", "100", "$2.10", "5"],
        ["SKU-003", "Bluetooth Speaker Mini", "$22.00", "20", "$19.80", "7"],
        ["SKU-004", "Laptop Stand Adjustable", "$18.00", "15", "$16.20", "10"],
        ["SKU-005", "Wireless Mouse Ergonomic", "$10.00", "50", "$8.75", "5"],
        ["SKU-006", "Phone Screen Protector", "$1.50", "200", "$1.20", "3"],
        ["SKU-007", "HDMI Cable 10ft", "$4.00", "100", "$3.40", "5"],
        ["SKU-008", "Webcam HD 1080p", "$25.00", "10", "$22.50", "12"],
        ["SKU-009", "Keyboard Mechanical RGB", "$35.00", "10", "$31.50", "10"],
        ["SKU-010", "Monitor Stand Dual", "$28.00", "10", "$25.20", "14"],
    ]

    table = Table(catalog_items, colWidths=[60, 170, 70, 40, 90, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ECF0F1")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#ECF0F1")]),
    ]))
    elements.append(Paragraph("<b>Product Pricing Table</b>", styles["Heading2"]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(table)
    elements.append(Spacer(1, 0.3 * inch))

    # Volume discount tiers
    elements.append(Paragraph("<b>Volume Discount Tiers</b>", styles["Heading2"]))
    discount_data = [
        ["Tier", "Order Quantity", "Discount"],
        ["Standard", "1 – 49 units", "0%"],
        ["Bronze", "50 – 99 units", "5%"],
        ["Silver", "100 – 249 units", "10%"],
        ["Gold", "250 – 499 units", "15%"],
        ["Platinum", "500+ units", "20%"],
    ]
    discount_table = Table(discount_data, colWidths=[80, 130, 80])
    discount_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#27AE60")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(discount_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Shipping and terms
    elements.append(Paragraph("<b>Shipping &amp; Terms</b>", styles["Heading2"]))
    elements.append(Paragraph(
        "Standard shipping: 5-7 business days. Expedited shipping available at 1.5x cost "
        "for 2-3 day delivery. All prices are FOB origin. Returns accepted within 30 days "
        "for defective items only. Bulk orders (500+ units) require 14 days advance notice.",
        styles["Normal"],
    ))

    doc.build(elements)
    logger.info("Created %s", output_path)


def generate_inventory_policy_pdf() -> None:
    """Create an inventory policy PDF with reorder rules, safety stock formulas, and approval thresholds."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output_path = DATA_DIR / "inventory_policy.pdf"
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Inventory Management Policy — 2024", styles["Title"]))
    elements.append(Spacer(1, 0.3 * inch))

    sections = [
        ("1. Reorder Point Policy", [
            "The reorder point (ROP) for each SKU is calculated as:",
            "    ROP = (Average Daily Demand × Lead Time in Days) + Safety Stock",
            "",
            "When current stock falls below the ROP, an automatic reorder alert is triggered. "
            "The procurement team has 24 hours to review and approve the recommended purchase order.",
            "",
            "For fast-moving items (daily demand > 20 units), the ROP is reviewed weekly. "
            "For slow-moving items (daily demand < 5 units), the ROP is reviewed monthly.",
        ]),
        ("2. Safety Stock Formula", [
            "Safety stock is calculated using the service level approach:",
            "    Safety Stock = Z × σ_d × √(Lead Time)",
            "",
            "Where:",
            "  - Z = service level factor (1.65 for 95% service level)",
            "  - σ_d = standard deviation of daily demand",
            "  - Lead Time = supplier lead time in days",
            "",
            "For critical items (Category A), we target a 98% service level (Z = 2.05).",
            "For standard items (Category B), we target a 95% service level (Z = 1.65).",
            "For low-priority items (Category C), we target a 90% service level (Z = 1.28).",
        ]),
        ("3. Economic Order Quantity (EOQ)", [
            "The optimal order quantity is determined by the EOQ formula:",
            "    EOQ = √((2 × Annual Demand × Order Cost) / Holding Cost per Unit)",
            "",
            "Order Cost: $25 per purchase order (administrative + shipping)",
            "Holding Cost: 20% of unit cost per year",
            "",
            "The EOQ is adjusted upward to meet Minimum Order Quantities (MOQ) set by suppliers.",
        ]),
        ("4. Approval Thresholds", [
            "Purchase orders are subject to the following approval requirements:",
            "  - Orders under $1,000: Auto-approved by the system",
            "  - Orders $1,000 – $5,000: Procurement Manager approval required",
            "  - Orders $5,000 – $25,000: Procurement Director approval required",
            "  - Orders over $25,000: VP of Operations approval required",
            "",
            "Emergency orders (stockout imminent within 48 hours) may bypass standard approval "
            "with post-facto review within 5 business days.",
        ]),
        ("5. ABC Classification", [
            "All SKUs are classified quarterly using the ABC method:",
            "  - Category A: Top 20% of SKUs by revenue (80% of total sales value)",
            "  - Category B: Next 30% of SKUs by revenue (15% of total sales value)",
            "  - Category C: Remaining 50% of SKUs (5% of total sales value)",
            "",
            "Category A items receive daily monitoring and weekly demand forecasting.",
            "Category B items receive weekly monitoring and monthly forecasting.",
            "Category C items receive monthly monitoring and quarterly forecasting.",
        ]),
    ]

    for heading, paragraphs in sections:
        elements.append(Paragraph(heading, styles["Heading2"]))
        elements.append(Spacer(1, 0.1 * inch))
        for para in paragraphs:
            if para == "":
                elements.append(Spacer(1, 0.1 * inch))
            else:
                elements.append(Paragraph(para, styles["Normal"]))
        elements.append(Spacer(1, 0.2 * inch))

    doc.build(elements)
    logger.info("Created %s", output_path)


def generate_market_report_pdf() -> None:
    """Create a market report PDF with demand trends and seasonal factors."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output_path = DATA_DIR / "market_report_electronics_2024.pdf"
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Electronics Market Report — 2024 Outlook", styles["Title"]))
    elements.append(Spacer(1, 0.3 * inch))

    sections = [
        ("Executive Summary", [
            "The consumer electronics market is projected to grow 6.2% in 2024, driven by "
            "strong demand in wireless audio, smart home devices, and computer peripherals. "
            "Supply chain disruptions have largely stabilized, though component shortages in "
            "Bluetooth chips may impact Q3 production. This report provides demand forecasts "
            "and seasonal adjustment factors for inventory planning.",
        ]),
        ("1. Wireless Audio Segment (Headphones, Speakers)", [
            "The wireless audio market continues its strong growth trajectory with a projected "
            "12% year-over-year increase. Key drivers include remote work adoption and fitness "
            "trends driving demand for true wireless earbuds and portable speakers.",
            "",
            "Seasonal Demand Factors:",
            "  - Q1 (Jan-Mar): 0.85x baseline — post-holiday slowdown",
            "  - Q2 (Apr-Jun): 1.05x baseline — spring promotions, graduation gifts",
            "  - Q3 (Jul-Sep): 1.15x baseline — back-to-school, Amazon Prime Day",
            "  - Q4 (Oct-Dec): 1.50x baseline — Black Friday, holiday gifting peak",
            "",
            "Lead time advisory: Bluetooth chip shortages may extend lead times by 3-5 days "
            "in Q3 2024. Recommend pre-ordering Q3 inventory by end of Q2.",
        ]),
        ("2. Computer Accessories Segment (Cables, Stands, Mice)", [
            "Computer accessories remain a stable category with 4% projected growth. The "
            "shift to USB-C continues to drive replacement purchases. Ergonomic products "
            "(standing desks, ergonomic mice) show 18% growth as companies invest in "
            "employee wellness.",
            "",
            "Seasonal Demand Factors:",
            "  - Q1: 0.90x baseline",
            "  - Q2: 1.00x baseline",
            "  - Q3: 1.20x baseline — back-to-school, new laptop purchases",
            "  - Q4: 1.30x baseline — corporate year-end spending",
            "",
            "Price trend: USB-C cables facing 8% price decline due to increased competition. "
            "Recommend negotiating lower supplier contracts for H2 2024.",
        ]),
        ("3. Competitive Landscape", [
            "Major online retailers are expanding same-day delivery, increasing pressure on "
            "inventory availability. Stockout penalty is now estimated at 2.5x the margin "
            "of the lost sale (including customer lifetime value impact).",
            "",
            "Key competitor actions to monitor:",
            "  - Amazon expanding private label electronics accessories",
            "  - Best Buy launching subscription model for accessories",
            "  - Walmart increasing electronics shelf space by 15%",
        ]),
        ("4. Supply Chain Outlook", [
            "Global logistics costs have decreased 22% from 2023 peaks but remain 35% above "
            "pre-pandemic levels. Key risks include:",
            "  - Red Sea shipping disruptions adding 10-14 days to Asia-origin shipments",
            "  - Semiconductor allocation still constrained for Bluetooth and WiFi chips",
            "  - Potential tariff changes on Chinese electronics imports in Q4",
            "",
            "Recommendation: Maintain 15-20% safety stock buffer for Asia-sourced items and "
            "diversify to at least 2 suppliers per critical SKU category.",
        ]),
    ]

    for heading, paragraphs in sections:
        elements.append(Paragraph(heading, styles["Heading2"]))
        elements.append(Spacer(1, 0.1 * inch))
        for para in paragraphs:
            if para == "":
                elements.append(Spacer(1, 0.1 * inch))
            else:
                elements.append(Paragraph(para, styles["Normal"]))
        elements.append(Spacer(1, 0.2 * inch))

    doc.build(elements)
    logger.info("Created %s", output_path)


def generate_sales_history_csv() -> None:
    """Generate 12 months of daily sales data for 5 SKUs."""
    output_path = DATA_DIR / "sales_history.csv"
    random.seed(42)

    base_demand = {
        "SKU-001": 8, "SKU-002": 25, "SKU-003": 5,
        "SKU-004": 4, "SKU-005": 10,
    }
    prices = {
        "SKU-001": 49.99, "SKU-002": 12.99, "SKU-003": 79.99,
        "SKU-004": 59.99, "SKU-005": 34.99,
    }
    seasonality = {
        1: 0.8, 2: 0.75, 3: 0.85, 4: 0.9, 5: 1.0, 6: 1.05,
        7: 1.1, 8: 1.15, 9: 1.0, 10: 1.1, 11: 1.4, 12: 1.6,
    }

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "sku", "quantity_sold", "unit_price", "total_revenue", "channel"])

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        current = start
        while current <= end:
            for sku, base in base_demand.items():
                factor = seasonality[current.month]
                dow_factor = 1.15 if current.weekday() >= 5 else 1.0
                qty = max(0, int(base * factor * dow_factor + random.gauss(0, base * 0.2)))
                price = prices[sku]
                writer.writerow([
                    current.strftime("%Y-%m-%d"),
                    sku,
                    qty,
                    price,
                    round(qty * price, 2),
                    random.choice(["online", "online", "online", "retail"]),
                ])
            current += timedelta(days=1)

    logger.info("Created %s", output_path)


def generate_supplier_performance_csv() -> None:
    """Generate supplier performance data."""
    output_path = DATA_DIR / "supplier_performance.csv"

    rows = [
        {
            "supplier_id": "SUP-001",
            "supplier_name": "TechDistributors Inc",
            "overall_score": 94,
            "on_time_delivery_pct": 92.5,
            "quality_score": 96,
            "defect_rate_pct": 1.2,
            "avg_lead_time_days": 7,
            "price_competitiveness": 88,
            "communication_score": 91,
            "total_orders_2024": 145,
            "total_value_2024": 287500.00,
        },
        {
            "supplier_id": "SUP-002",
            "supplier_name": "GlobalElectro Supply",
            "overall_score": 82,
            "on_time_delivery_pct": 86.0,
            "quality_score": 84,
            "defect_rate_pct": 2.5,
            "avg_lead_time_days": 12,
            "price_competitiveness": 92,
            "communication_score": 78,
            "total_orders_2024": 89,
            "total_value_2024": 156000.00,
        },
        {
            "supplier_id": "SUP-003",
            "supplier_name": "PrimeParts Wholesale",
            "overall_score": 97,
            "on_time_delivery_pct": 96.0,
            "quality_score": 98,
            "defect_rate_pct": 0.8,
            "avg_lead_time_days": 5,
            "price_competitiveness": 85,
            "communication_score": 95,
            "total_orders_2024": 112,
            "total_value_2024": 198000.00,
        },
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Created %s", output_path)


def main() -> None:
    """Generate all sample data files."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Generating sample data in %s", DATA_DIR)

    generate_supplier_catalog_pdf()
    generate_inventory_policy_pdf()
    generate_market_report_pdf()
    generate_sales_history_csv()
    generate_supplier_performance_csv()

    logger.info("All sample data files generated successfully.")


if __name__ == "__main__":
    main()
