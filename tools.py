"""
tools.py — LangChain tools for the Dynamic Inventory Reorder Agent.

Implements 7 functional tools with @tool decorators and Pydantic input schemas:
  1. get_sales_data       — queries SQLite sales_history
  2. get_current_inventory — returns current stock levels
  3. forecast_demand       — moving-average demand forecast
  4. query_supplier_catalog— queries ChromaDB for supplier info
  5. calculate_order_qty   — EOQ formula calculation
  6. generate_purchase_order — creates a purchase order dict
  7. send_alert            — logs alerts to file and console
"""

import logging
import math
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "inventory.db"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
ALERTS_LOG = Path(__file__).parent / "alerts.log"
COLLECTION_NAME = "inventory_agent_kb"


# ---------------------------------------------------------------------------
# Pydantic Input Schemas
# ---------------------------------------------------------------------------

class GetSalesDataInput(BaseModel):
    """Input schema for get_sales_data tool."""
    sku: str = Field(..., description="SKU identifier e.g. SKU-001")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")


class GetCurrentInventoryInput(BaseModel):
    """Input schema for get_current_inventory tool."""
    sku: str = Field(..., description="SKU identifier e.g. SKU-001")


class ForecastDemandInput(BaseModel):
    """Input schema for forecast_demand tool."""
    sku: str = Field(..., description="SKU identifier e.g. SKU-001")
    days_ahead: int = Field(..., description="Number of days to forecast ahead", ge=1, le=365)


class QuerySupplierCatalogInput(BaseModel):
    """Input schema for query_supplier_catalog tool."""
    sku: str = Field(..., description="SKU identifier or product name to search for")


class CalculateOrderQtyInput(BaseModel):
    """Input schema for calculate_order_qty tool."""
    sku: str = Field(..., description="SKU identifier e.g. SKU-001")
    forecast_demand: float = Field(..., description="Forecasted demand in units per day")
    current_stock: int = Field(..., description="Current stock level in units")
    lead_time_days: int = Field(..., description="Supplier lead time in days")


class GeneratePurchaseOrderInput(BaseModel):
    """Input schema for generate_purchase_order tool."""
    sku: str = Field(..., description="SKU identifier e.g. SKU-001")
    quantity: int = Field(..., description="Number of units to order")
    supplier_name: str = Field(..., description="Name of the supplier")
    unit_price: float = Field(..., description="Unit price in dollars")


class SendAlertInput(BaseModel):
    """Input schema for send_alert tool."""
    message: str = Field(..., description="Alert message text")
    urgency_level: str = Field(
        ..., description="Urgency level: 'critical', 'high', 'medium', or 'low'"
    )


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

@tool("get_sales_data", args_schema=GetSalesDataInput)
def get_sales_data(sku: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Retrieves historical sales data for a given SKU from the SQLite database.
    Use this tool when you need to analyze past demand patterns for forecasting."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sale_date, quantity_sold, unit_price, total_revenue, channel
            FROM sales_history
            WHERE sku = ? AND sale_date BETWEEN ? AND ?
            ORDER BY sale_date
            """,
            (sku, start_date, end_date),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"error": f"No sales data found for {sku} between {start_date} and {end_date}"}

        total_qty = sum(r[1] for r in rows)
        total_revenue = sum(r[3] for r in rows)
        avg_daily = total_qty / len(rows) if rows else 0

        return {
            "sku": sku,
            "period": f"{start_date} to {end_date}",
            "total_days": len(rows),
            "total_quantity_sold": total_qty,
            "total_revenue": round(total_revenue, 2),
            "average_daily_demand": round(avg_daily, 2),
            "min_daily": min(r[1] for r in rows),
            "max_daily": max(r[1] for r in rows),
            "sample_records": [
                {"date": r[0], "qty": r[1], "price": r[2], "revenue": r[3]}
                for r in rows[:5]
            ],
        }
    except Exception as e:
        logger.error("get_sales_data failed: %s", e)
        return {"error": str(e)}


@tool("get_current_inventory", args_schema=GetCurrentInventoryInput)
def get_current_inventory(sku: str) -> dict[str, Any]:
    """Returns the current inventory level, reorder point, and safety stock for a SKU.
    Use this tool to check if a SKU needs reordering by comparing stock to reorder point."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sku, product_name, category, current_stock, reorder_point,
                   safety_stock, unit_cost, unit_price, warehouse_location, last_updated
            FROM current_inventory WHERE sku = ?
            """,
            (sku,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"error": f"SKU {sku} not found in inventory"}

        current_stock = row[3]
        reorder_point = row[4]
        needs_reorder = current_stock <= reorder_point

        return {
            "sku": row[0],
            "product_name": row[1],
            "category": row[2],
            "current_stock": current_stock,
            "reorder_point": reorder_point,
            "safety_stock": row[5],
            "unit_cost": row[6],
            "unit_price": row[7],
            "warehouse_location": row[8],
            "last_updated": row[9],
            "needs_reorder": needs_reorder,
            "stock_status": "CRITICAL" if current_stock <= row[5] else ("LOW" if needs_reorder else "OK"),
        }
    except Exception as e:
        logger.error("get_current_inventory failed: %s", e)
        return {"error": str(e)}


@tool("forecast_demand", args_schema=ForecastDemandInput)
def forecast_demand(sku: str, days_ahead: int) -> dict[str, Any]:
    """Calculates a demand forecast using moving average from historical sales data.
    Use this tool when you need to predict future demand for reorder planning."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Get last 90 days of sales data for the moving average
        cursor.execute(
            """
            SELECT sale_date, quantity_sold
            FROM sales_history
            WHERE sku = ?
            ORDER BY sale_date DESC
            LIMIT 90
            """,
            (sku,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"error": f"No historical data found for {sku}"}

        daily_sales = [r[1] for r in rows]

        # 7-day moving average
        ma_7 = sum(daily_sales[:7]) / min(7, len(daily_sales))
        # 30-day moving average
        ma_30 = sum(daily_sales[:30]) / min(30, len(daily_sales))
        # 90-day moving average
        ma_90 = sum(daily_sales) / len(daily_sales)

        # Weighted forecast (recent data weighted more heavily)
        forecast_daily = round(0.5 * ma_7 + 0.3 * ma_30 + 0.2 * ma_90, 2)
        forecast_total = round(forecast_daily * days_ahead, 2)

        # Standard deviation for safety stock calculation
        std_dev = (
            sum((x - ma_90) ** 2 for x in daily_sales) / len(daily_sales)
        ) ** 0.5

        return {
            "sku": sku,
            "days_ahead": days_ahead,
            "forecast_daily_demand": forecast_daily,
            "forecast_total_demand": forecast_total,
            "moving_avg_7d": round(ma_7, 2),
            "moving_avg_30d": round(ma_30, 2),
            "moving_avg_90d": round(ma_90, 2),
            "demand_std_dev": round(std_dev, 2),
            "confidence_note": "Weighted average: 50% 7-day MA + 30% 30-day MA + 20% 90-day MA",
        }
    except Exception as e:
        logger.error("forecast_demand failed: %s", e)
        return {"error": str(e)}


@tool("query_supplier_catalog", args_schema=QuerySupplierCatalogInput)
def query_supplier_catalog(sku: str) -> dict[str, Any]:
    """Queries the ChromaDB knowledge base for supplier catalog information about a SKU.
    Use this tool when you need pricing, MOQ, lead times, or supplier details for a product."""
    try:
        from langchain_community.vectorstores import Chroma
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings,
        )

        results = vectorstore.similarity_search(
            query=f"pricing and lead time for {sku}",
            k=3,
            filter={"doc_type": "supplier_catalog"},
        )

        if not results:
            return {"error": f"No supplier catalog data found for {sku}"}

        return {
            "sku": sku,
            "results_count": len(results),
            "catalog_excerpts": [
                {
                    "content": doc.page_content[:500],
                    "metadata": doc.metadata,
                }
                for doc in results
            ],
        }
    except Exception as e:
        logger.error("query_supplier_catalog failed: %s", e)
        return {"error": str(e)}


@tool("calculate_order_qty", args_schema=CalculateOrderQtyInput)
def calculate_order_qty(
    sku: str,
    forecast_demand: float,
    current_stock: int,
    lead_time_days: int,
) -> dict[str, Any]:
    """Calculates the optimal order quantity using the Economic Order Quantity (EOQ) formula.
    Use this tool after forecasting demand to determine how many units to order."""
    try:
        # EOQ parameters
        ORDER_COST = 25.0  # $ per purchase order (admin + shipping)
        HOLDING_COST_PCT = 0.20  # 20% of unit cost per year

        # Get unit cost from database
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT unit_cost FROM current_inventory WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"error": f"SKU {sku} not found in inventory"}

        unit_cost = row[0]
        holding_cost = unit_cost * HOLDING_COST_PCT

        # Annual demand estimate
        annual_demand = forecast_demand * 365

        # EOQ formula: sqrt((2 * annual_demand * order_cost) / holding_cost)
        if holding_cost <= 0 or annual_demand <= 0:
            return {"error": "EOQ calculation requires positive holding_cost and annual_demand values"}

        eoq = math.sqrt((2 * annual_demand * ORDER_COST) / holding_cost)
        eoq_rounded = max(1, round(eoq))

        # Calculate reorder quantity considering current stock and lead time demand
        lead_time_demand = forecast_demand * lead_time_days
        net_requirement = max(0, lead_time_demand - current_stock)

        # Final order quantity: max of EOQ and net requirement
        recommended_qty = max(eoq_rounded, math.ceil(net_requirement))

        return {
            "sku": sku,
            "eoq_calculated": eoq_rounded,
            "annual_demand_estimate": round(annual_demand),
            "lead_time_demand": round(lead_time_demand, 1),
            "current_stock": current_stock,
            "net_requirement": round(net_requirement, 1),
            "recommended_order_qty": recommended_qty,
            "unit_cost": unit_cost,
            "order_cost_per_po": ORDER_COST,
            "holding_cost_pct": f"{HOLDING_COST_PCT*100}%",
            "estimated_total_cost": round(recommended_qty * unit_cost, 2),
        }
    except Exception as e:
        logger.error("calculate_order_qty failed: %s", e)
        return {"error": str(e)}


@tool("generate_purchase_order", args_schema=GeneratePurchaseOrderInput)
def generate_purchase_order(
    sku: str,
    quantity: int,
    supplier_name: str,
    unit_price: float,
) -> dict[str, Any]:
    """Generates a purchase order document with a unique PO number, line items, and total cost.
    Use this tool to create a formal purchase order after determining order quantity and supplier."""
    try:
        po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        total_cost = round(quantity * unit_price, 2)

        # Get product name from DB
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT product_name FROM current_inventory WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        product_name = row[0] if row else sku

        purchase_order = {
            "po_number": po_number,
            "status": "draft",
            "created_at": datetime.now().isoformat(),
            "supplier": supplier_name,
            "line_items": [
                {
                    "sku": sku,
                    "product_name": product_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": total_cost,
                }
            ],
            "subtotal": total_cost,
            "shipping_estimate": round(total_cost * 0.05, 2),
            "total_cost": round(total_cost * 1.05, 2),
            "payment_terms": "Net 30",
            "notes": f"Auto-generated PO for {sku} reorder",
        }

        # Store PO in database
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO purchase_orders (po_number, sku, supplier_id, quantity, unit_price, total_cost, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (po_number, sku, supplier_name, quantity, unit_price, total_cost, "draft", datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as db_err:
            logger.warning("Could not save PO to database: %s", db_err)

        logger.info("Generated Purchase Order %s for %d units of %s", po_number, quantity, sku)
        return purchase_order

    except Exception as e:
        logger.error("generate_purchase_order failed: %s", e)
        return {"error": str(e)}


@tool("send_alert", args_schema=SendAlertInput)
def send_alert(message: str, urgency_level: str) -> dict[str, str]:
    """Sends an alert notification by logging to alerts.log and printing to console.
    Use this tool to notify the procurement team about critical inventory situations."""
    try:
        timestamp = datetime.now().isoformat()
        alert_entry = f"[{timestamp}] [{urgency_level.upper()}] {message}"

        # Log to alerts file
        with open(ALERTS_LOG, "a") as f:
            f.write(alert_entry + "\n")

        # Also log via logging module
        if urgency_level.lower() == "critical":
            logger.critical("ALERT: %s", message)
        elif urgency_level.lower() == "high":
            logger.warning("ALERT: %s", message)
        else:
            logger.info("ALERT: %s", message)

        return {
            "status": "sent",
            "timestamp": timestamp,
            "urgency": urgency_level.upper(),
            "message": message,
            "logged_to": str(ALERTS_LOG),
        }
    except Exception as e:
        logger.error("send_alert failed: %s", e)
        return {"error": str(e)}


# Collect all tools for easy import
ALL_TOOLS = [
    get_sales_data,
    get_current_inventory,
    forecast_demand,
    query_supplier_catalog,
    calculate_order_qty,
    generate_purchase_order,
    send_alert,
]

# Research tools (Agent A)
RESEARCH_TOOLS = [
    get_sales_data,
    get_current_inventory,
    forecast_demand,
    query_supplier_catalog,
]

# Procurement tools (Agent B)
PROCUREMENT_TOOLS = [
    calculate_order_qty,
    generate_purchase_order,
    send_alert,
]


if __name__ == "__main__":
    # Quick standalone test of each tool
    print("Testing tools with SKU-001...\n")

    print("1. get_sales_data:")
    result = get_sales_data.invoke({"sku": "SKU-001", "start_date": "2024-01-01", "end_date": "2024-03-31"})
    print(f"   {result}\n")

    print("2. get_current_inventory:")
    result = get_current_inventory.invoke({"sku": "SKU-001"})
    print(f"   {result}\n")

    print("3. forecast_demand:")
    result = forecast_demand.invoke({"sku": "SKU-001", "days_ahead": 30})
    print(f"   {result}\n")

    print("5. calculate_order_qty:")
    result = calculate_order_qty.invoke({
        "sku": "SKU-001",
        "forecast_demand": 8.5,
        "current_stock": 35,
        "lead_time_days": 7,
    })
    print(f"   {result}\n")

    print("6. generate_purchase_order:")
    result = generate_purchase_order.invoke({
        "sku": "SKU-001",
        "quantity": 200,
        "supplier_name": "TechDistributors Inc",
        "unit_price": 15.00,
    })
    print(f"   {result}\n")

    print("7. send_alert:")
    result = send_alert.invoke({
        "message": "SKU-001 stock is below reorder point!",
        "urgency_level": "high",
    })
    print(f"   {result}\n")
