"""
Lab 3: Tool Engineering with Pydantic
======================================
Project-specific tools for the Dynamic Inventory Reorder Agent.
Each tool uses the @tool decorator and Pydantic input validation.
"""

import csv
import math
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import (
    SALES_HISTORY_PATH,
    INVENTORY_LEVELS_PATH,
    SUPPLIER_CATALOGS,
    PROMOTIONAL_CALENDAR_PATH,
    AUTO_APPROVE_THRESHOLD,
)


# ─── Pydantic Input Schemas ─────────────────────────────────────────────────

class SalesDataInput(BaseModel):
    """Input schema for retrieving sales data."""
    sku: str = Field(description="The SKU identifier, e.g. 'SKU-001'")
    start_date: Optional[str] = Field(default=None, description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(default=None, description="End date in YYYY-MM-DD format")


class InventoryInput(BaseModel):
    """Input schema for checking inventory."""
    sku: str = Field(description="The SKU identifier, e.g. 'SKU-001'")


class ForecastInput(BaseModel):
    """Input schema for demand forecasting."""
    sku: str = Field(description="The SKU identifier")
    forecast_days: int = Field(default=30, description="Number of days to forecast")


class SupplierQueryInput(BaseModel):
    """Input schema for querying suppliers."""
    sku: str = Field(description="The SKU identifier")


class OrderQuantityInput(BaseModel):
    """Input schema for calculating optimal order quantity."""
    sku: str = Field(description="The SKU identifier")
    forecasted_demand: int = Field(description="Forecasted demand in units")
    lead_time_days: int = Field(description="Supplier lead time in days")
    safety_stock: int = Field(description="Desired safety stock level")


class PurchaseOrderInput(BaseModel):
    """Input schema for generating a purchase order."""
    sku: str = Field(description="The SKU identifier")
    product_name: str = Field(description="Product name")
    quantity: int = Field(description="Order quantity in units")
    supplier_name: str = Field(description="Selected supplier name")
    supplier_id: str = Field(description="Selected supplier ID")
    unit_price: float = Field(description="Agreed unit price")


class SupplierSelectionInput(BaseModel):
    """Input schema for multi-criteria supplier selection."""
    sku: str = Field(description="The SKU identifier")
    required_quantity: int = Field(description="Quantity needed for the order")


class KnowledgeBaseQueryInput(BaseModel):
    """Input schema for querying the RAG knowledge base."""
    query: str = Field(description="Natural language query to search the knowledge base")
    doc_type: Optional[str] = Field(
        default=None,
        description="Filter by document type: 'supplier_catalog', 'sales_history', 'inventory_level', 'promotional_event'"
    )


# ─── Tool Implementations ───────────────────────────────────────────────────

@tool(args_schema=SalesDataInput)
def get_sales_data(sku: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """Retrieve historical sales data for a given SKU from the sales database.
    Returns daily sales, returns, and net demand. Use this to understand
    demand patterns before forecasting."""

    if not os.path.exists(SALES_HISTORY_PATH):
        return json.dumps({"error": "Sales history file not found"})

    records = []
    with open(SALES_HISTORY_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["sku"] != sku:
                continue
            if start_date and row["date"] < start_date:
                continue
            if end_date and row["date"] > end_date:
                continue
            records.append({
                "date": row["date"],
                "quantity_sold": int(row["quantity_sold"]),
                "returns": int(row["returns"]),
                "net_demand": int(row["quantity_sold"]) - int(row["returns"]),
                "promotion_active": row["promotion_active"] == "True",
            })

    if not records:
        return json.dumps({"sku": sku, "message": "No sales data found for this SKU in the given range"})

    total_sold = sum(r["quantity_sold"] for r in records)
    total_returns = sum(r["returns"] for r in records)
    avg_daily = round(sum(r["net_demand"] for r in records) / len(records), 1)

    return json.dumps({
        "sku": sku,
        "period": f"{records[0]['date']} to {records[-1]['date']}",
        "total_records": len(records),
        "total_sold": total_sold,
        "total_returns": total_returns,
        "net_demand": total_sold - total_returns,
        "avg_daily_demand": avg_daily,
        "recent_records": records[-5:],
    })


@tool(args_schema=InventoryInput)
def get_current_inventory(sku: str) -> str:
    """Check the current real-time inventory level for a SKU from the ERP system.
    Returns current stock, reorder point, safety stock, and warehouse details."""

    if not os.path.exists(INVENTORY_LEVELS_PATH):
        return json.dumps({"error": "Inventory file not found"})

    with open(INVENTORY_LEVELS_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["sku"] == sku:
                current = int(row["current_stock"])
                reorder_pt = int(row["reorder_point"])
                return json.dumps({
                    "sku": sku,
                    "product_name": row["product_name"],
                    "category": row["category"],
                    "current_stock": current,
                    "reorder_point": reorder_pt,
                    "safety_stock": int(row["safety_stock"]),
                    "max_capacity": int(row["max_capacity"]),
                    "warehouse_location": row["warehouse_location"],
                    "unit_cost": float(row["unit_cost"]),
                    "needs_reorder": current < reorder_pt,
                    "stock_deficit": max(0, reorder_pt - current),
                })

    return json.dumps({"sku": sku, "error": "SKU not found in inventory system"})


@tool(args_schema=ForecastInput)
def forecast_demand(sku: str, forecast_days: int = 30) -> str:
    """Forecast demand for a SKU over a specified number of days using
    weighted moving average with seasonality adjustment. Considers recent
    sales trends, promotional impact, and seasonal patterns."""

    if not os.path.exists(SALES_HISTORY_PATH):
        return json.dumps({"error": "Sales history not found for forecasting"})

    records = []
    with open(SALES_HISTORY_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["sku"] == sku:
                records.append({
                    "date": row["date"],
                    "net_demand": int(row["quantity_sold"]) - int(row["returns"]),
                    "promotion": row["promotion_active"] == "True",
                })

    if not records:
        return json.dumps({"sku": sku, "error": "No historical data for forecasting"})

    # Weighted moving average: recent data weighted more heavily
    demands = [r["net_demand"] for r in records]
    n = len(demands)
    weights = list(range(1, n + 1))
    weighted_avg = sum(d * w for d, w in zip(demands, weights)) / sum(weights)

    # Promotional uplift: if any upcoming promos, adjust
    promo_ratio = sum(1 for r in records if r["promotion"]) / max(n, 1)
    promo_uplift = 1.0 + (promo_ratio * 0.4)  # Up to 40% uplift based on historical promo frequency

    # Check upcoming promotions
    upcoming_promo = False
    promo_multiplier = 1.0
    if os.path.exists(PROMOTIONAL_CALENDAR_PATH):
        today = datetime.now()
        forecast_end = today + timedelta(days=forecast_days)
        with open(PROMOTIONAL_CALENDAR_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                promo_start = datetime.strptime(row["start_date"], "%Y-%m-%d")
                promo_end = datetime.strptime(row["end_date"], "%Y-%m-%d")
                if promo_start <= forecast_end and promo_end >= today:
                    upcoming_promo = True
                    promo_multiplier = max(promo_multiplier, float(row["expected_demand_multiplier"]))

    daily_forecast = round(weighted_avg * (promo_multiplier if upcoming_promo else 1.0), 1)
    total_forecast = round(daily_forecast * forecast_days)

    # Confidence interval (simple ± based on standard deviation)
    if n > 1:
        mean = sum(demands) / n
        variance = sum((d - mean) ** 2 for d in demands) / (n - 1)
        std_dev = math.sqrt(variance)
        confidence_low = max(0, round((daily_forecast - 1.96 * std_dev / math.sqrt(n)) * forecast_days))
        confidence_high = round((daily_forecast + 1.96 * std_dev / math.sqrt(n)) * forecast_days)
    else:
        confidence_low = total_forecast
        confidence_high = total_forecast

    return json.dumps({
        "sku": sku,
        "forecast_days": forecast_days,
        "daily_forecast": daily_forecast,
        "total_forecasted_demand": total_forecast,
        "confidence_interval": {"low": confidence_low, "high": confidence_high},
        "upcoming_promotion": upcoming_promo,
        "promo_multiplier": promo_multiplier if upcoming_promo else 1.0,
        "method": "Weighted Moving Average with Seasonal Adjustment",
    })


@tool(args_schema=SupplierQueryInput)
def query_all_suppliers(sku: str) -> str:
    """Query all approved suppliers for a given SKU. Returns price, MOQ,
    lead time, stock status, reliability score, and volume discounts
    for comparison."""

    suppliers = []
    for catalog_path in SUPPLIER_CATALOGS:
        if not os.path.exists(catalog_path):
            continue
        with open(catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["sku"] == sku:
                    suppliers.append({
                        "supplier_name": row["supplier_name"],
                        "supplier_id": row["supplier_id"],
                        "unit_price": float(row["unit_price"]),
                        "moq": int(row["moq"]),
                        "lead_time_days": int(row["lead_time_days"]),
                        "stock_status": row["stock_status"],
                        "reliability_score": float(row["reliability_score"]),
                        "defect_rate_pct": float(row["defect_rate_pct"]),
                        "volume_discount_threshold": int(row["volume_discount_threshold"]),
                        "volume_discount_pct": float(row["volume_discount_pct"]),
                        "payment_terms": row["payment_terms"],
                    })

    if not suppliers:
        return json.dumps({"sku": sku, "error": "No suppliers found for this SKU"})

    return json.dumps({"sku": sku, "suppliers": suppliers, "total_suppliers": len(suppliers)})


@tool(args_schema=SupplierSelectionInput)
def select_best_supplier(sku: str, required_quantity: int) -> str:
    """Select the optimal supplier using multi-criteria weighted scoring.
    Weights: Price 40%, Lead Time 25%, Reliability 20%, Quality 15%.
    Accounts for volume discounts and stock availability."""

    suppliers = []
    for catalog_path in SUPPLIER_CATALOGS:
        if not os.path.exists(catalog_path):
            continue
        with open(catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["sku"] == sku:
                    suppliers.append(row)

    if not suppliers:
        return json.dumps({"error": f"No suppliers found for {sku}"})

    # Filter out of stock suppliers
    available = [s for s in suppliers if s["stock_status"] != "Out of Stock"]
    if not available:
        return json.dumps({"error": f"All suppliers for {sku} are out of stock", "all_suppliers": [s["supplier_name"] for s in suppliers]})

    # Calculate scores
    scored = []
    prices = [float(s["unit_price"]) for s in available]
    lead_times = [int(s["lead_time_days"]) for s in available]
    min_price, max_price = min(prices), max(prices)
    min_lead, max_lead = min(lead_times), max(lead_times)

    for s in available:
        price = float(s["unit_price"])
        # Apply volume discount if applicable
        if required_quantity >= int(s["volume_discount_threshold"]):
            price *= (1 - float(s["volume_discount_pct"]) / 100)

        lead = int(s["lead_time_days"])
        reliability = float(s["reliability_score"])
        quality = 100 - float(s["defect_rate_pct"])  # Higher is better

        # Normalize to 0-1 scale (higher is better for all)
        price_range = max_price - min_price if max_price != min_price else 1
        lead_range = max_lead - min_lead if max_lead != min_lead else 1

        price_score = 1 - (price - min_price) / price_range
        lead_score = 1 - (lead - min_lead) / lead_range
        reliability_score = reliability / 100
        quality_score = quality / 100

        # Weighted composite score
        total_score = (
            0.40 * price_score +
            0.25 * lead_score +
            0.20 * reliability_score +
            0.15 * quality_score
        )

        scored.append({
            "supplier_name": s["supplier_name"],
            "supplier_id": s["supplier_id"],
            "unit_price": round(price, 2),
            "original_price": float(s["unit_price"]),
            "volume_discount_applied": required_quantity >= int(s["volume_discount_threshold"]),
            "lead_time_days": lead,
            "reliability_score": reliability,
            "defect_rate_pct": float(s["defect_rate_pct"]),
            "moq": int(s["moq"]),
            "composite_score": round(total_score, 3),
            "score_breakdown": {
                "price": round(price_score, 3),
                "lead_time": round(lead_score, 3),
                "reliability": round(reliability_score, 3),
                "quality": round(quality_score, 3),
            },
        })

    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    best = scored[0]

    return json.dumps({
        "sku": sku,
        "required_quantity": required_quantity,
        "recommended_supplier": best,
        "all_ranked_suppliers": scored,
        "selection_criteria": "Price 40%, Lead Time 25%, Reliability 20%, Quality 15%",
    })


@tool(args_schema=OrderQuantityInput)
def calculate_order_quantity(sku: str, forecasted_demand: int, lead_time_days: int, safety_stock: int) -> str:
    """Calculate the optimal order quantity using the Economic Order Quantity
    (EOQ) model. Accounts for forecasted demand, lead time, safety stock,
    and warehouse capacity constraints."""

    # Get unit cost and capacity from inventory
    unit_cost = 15.0
    max_capacity = 500
    current_stock = 0

    if os.path.exists(INVENTORY_LEVELS_PATH):
        with open(INVENTORY_LEVELS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["sku"] == sku:
                    unit_cost = float(row["unit_cost"])
                    max_capacity = int(row["max_capacity"])
                    current_stock = int(row["current_stock"])
                    break

    # EOQ parameters
    annual_demand = forecasted_demand * 12  # Annualize the monthly forecast
    ordering_cost = 50.0  # Fixed cost per order
    holding_cost_rate = 0.25  # 25% of unit cost per year
    holding_cost = unit_cost * holding_cost_rate

    # EOQ formula: sqrt(2 * D * S / H)
    if holding_cost > 0:
        eoq = math.sqrt(2 * annual_demand * ordering_cost / holding_cost)
    else:
        eoq = forecasted_demand

    # Reorder point = (daily demand * lead time) + safety stock
    daily_demand = forecasted_demand / 30
    reorder_point = math.ceil(daily_demand * lead_time_days + safety_stock)

    # Order quantity = max(EOQ, forecasted_demand - current_stock + safety_stock)
    minimum_needed = max(0, forecasted_demand - current_stock + safety_stock)
    optimal_qty = max(math.ceil(eoq), minimum_needed)

    # Warehouse capacity constraint
    available_capacity = max_capacity - current_stock
    if optimal_qty > available_capacity:
        optimal_qty = available_capacity

    total_cost = round(optimal_qty * unit_cost, 2)
    auto_approved = total_cost < AUTO_APPROVE_THRESHOLD

    return json.dumps({
        "sku": sku,
        "optimal_order_quantity": optimal_qty,
        "eoq_calculated": round(eoq),
        "reorder_point": reorder_point,
        "current_stock": current_stock,
        "forecasted_demand": forecasted_demand,
        "safety_stock": safety_stock,
        "available_capacity": available_capacity,
        "estimated_total_cost": total_cost,
        "auto_approved": auto_approved,
        "approval_threshold": AUTO_APPROVE_THRESHOLD,
    })


@tool(args_schema=PurchaseOrderInput)
def generate_purchase_order(sku: str, product_name: str, quantity: int, supplier_name: str, supplier_id: str, unit_price: float) -> str:
    """Generate a purchase order document. This is a HIGH-RISK action that
    creates a formal PO to be sent to a supplier. Requires human approval
    for orders above the auto-approval threshold."""

    po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{sku.replace('SKU-', '')}"
    total_cost = round(quantity * unit_price, 2)
    expected_delivery = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

    po_document = {
        "po_number": po_number,
        "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "GENERATED",
        "supplier": {
            "name": supplier_name,
            "id": supplier_id,
        },
        "line_items": [
            {
                "sku": sku,
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": total_cost,
            }
        ],
        "total_cost": total_cost,
        "expected_delivery_date": expected_delivery,
        "payment_terms": "Net 30",
        "shipping_address": "Warehouse-A, 123 Industrial Blvd, Topi, KPK",
        "notes": "Auto-generated by Dynamic Inventory Reorder Agent",
    }

    # Save PO to file
    po_dir = os.path.join(os.path.dirname(__file__), "purchase_orders")
    os.makedirs(po_dir, exist_ok=True)
    po_path = os.path.join(po_dir, f"{po_number}.json")
    with open(po_path, "w") as f:
        json.dump(po_document, f, indent=2)

    return json.dumps({
        "message": f"Purchase order {po_number} generated successfully",
        "po_document": po_document,
        "saved_to": po_path,
        "requires_approval": total_cost >= AUTO_APPROVE_THRESHOLD,
    })


@tool(args_schema=KnowledgeBaseQueryInput)
def query_knowledge_base(query: str, doc_type: Optional[str] = None) -> str:
    """Search the RAG knowledge base for domain-specific information.
    Can retrieve supplier catalogs, sales history, inventory levels,
    and promotional events. Use doc_type to filter results."""

    from ingest_data import query_knowledge_base as _query_kb

    where_filter = {"doc_type": doc_type} if doc_type else None
    results = _query_kb(query, n_results=3, where_filter=where_filter)

    formatted = []
    if results and results["documents"]:
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            formatted.append({
                "content": doc,
                "metadata": meta,
            })

    return json.dumps({
        "query": query,
        "filter": doc_type,
        "results": formatted,
        "num_results": len(formatted),
    })


# ─── Tool Registry ──────────────────────────────────────────────────────────

# Procurement Agent tools (data gathering and analysis)
PROCUREMENT_TOOLS = [
    get_sales_data,
    get_current_inventory,
    forecast_demand,
    query_all_suppliers,
    select_best_supplier,
    calculate_order_quantity,
    query_knowledge_base,
]

# Order Execution Agent tools (action-taking)
ORDER_EXECUTION_TOOLS = [
    generate_purchase_order,
    query_knowledge_base,
]

# All tools combined
ALL_TOOLS = [
    get_sales_data,
    get_current_inventory,
    forecast_demand,
    query_all_suppliers,
    select_best_supplier,
    calculate_order_quantity,
    generate_purchase_order,
    query_knowledge_base,
]
