"""
setup_database.py — Creates and populates the SQLite inventory database.

Creates tables for sales_history, current_inventory, suppliers, and
purchase_orders, then populates them with realistic data for SKU-001
through SKU-005.
"""

import sqlite3
import logging
import random
from pathlib import Path
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "inventory.db"

# SKU definitions with realistic electronics products
SKU_CATALOG = {
    "SKU-001": {
        "name": "Wireless Headphones Pro",
        "category": "Audio",
        "unit_cost": 15.00,
        "unit_price": 49.99,
        "reorder_point": 50,
        "safety_stock": 20,
        "current_stock": 35,
        "warehouse_location": "A-12",
    },
    "SKU-002": {
        "name": "USB-C Charging Cable 6ft",
        "category": "Accessories",
        "unit_cost": 2.50,
        "unit_price": 12.99,
        "reorder_point": 200,
        "safety_stock": 80,
        "current_stock": 450,
        "warehouse_location": "B-03",
    },
    "SKU-003": {
        "name": "Bluetooth Speaker Mini",
        "category": "Audio",
        "unit_cost": 22.00,
        "unit_price": 79.99,
        "reorder_point": 40,
        "safety_stock": 15,
        "current_stock": 28,
        "warehouse_location": "A-15",
    },
    "SKU-004": {
        "name": "Laptop Stand Adjustable",
        "category": "Accessories",
        "unit_cost": 18.00,
        "unit_price": 59.99,
        "reorder_point": 30,
        "safety_stock": 10,
        "current_stock": 65,
        "warehouse_location": "C-07",
    },
    "SKU-005": {
        "name": "Wireless Mouse Ergonomic",
        "category": "Peripherals",
        "unit_cost": 10.00,
        "unit_price": 34.99,
        "reorder_point": 60,
        "safety_stock": 25,
        "current_stock": 42,
        "warehouse_location": "B-09",
    },
}

SUPPLIERS = [
    {
        "id": "SUP-001",
        "name": "TechDistributors Inc",
        "contact_email": "orders@techdist.com",
        "phone": "+1-555-0101",
        "lead_time_days": 7,
        "reliability_score": 0.94,
        "on_time_delivery_pct": 92.5,
        "defect_rate_pct": 1.2,
        "payment_terms": "Net 30",
    },
    {
        "id": "SUP-002",
        "name": "GlobalElectro Supply",
        "contact_email": "sales@globalelectro.com",
        "phone": "+1-555-0202",
        "lead_time_days": 12,
        "reliability_score": 0.88,
        "on_time_delivery_pct": 86.0,
        "defect_rate_pct": 2.5,
        "payment_terms": "Net 45",
    },
    {
        "id": "SUP-003",
        "name": "PrimeParts Wholesale",
        "contact_email": "info@primeparts.com",
        "phone": "+1-555-0303",
        "lead_time_days": 5,
        "reliability_score": 0.97,
        "on_time_delivery_pct": 96.0,
        "defect_rate_pct": 0.8,
        "payment_terms": "Net 30",
    },
]


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables for the inventory system."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            quantity_sold INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_revenue REAL NOT NULL,
            channel TEXT DEFAULT 'online'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS current_inventory (
            sku TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            current_stock INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            safety_stock INTEGER NOT NULL,
            unit_cost REAL NOT NULL,
            unit_price REAL NOT NULL,
            warehouse_location TEXT,
            last_updated TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contact_email TEXT,
            phone TEXT,
            lead_time_days INTEGER NOT NULL,
            reliability_score REAL,
            on_time_delivery_pct REAL,
            defect_rate_pct REAL,
            payment_terms TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_number TEXT PRIMARY KEY,
            sku TEXT NOT NULL,
            supplier_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_cost REAL NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at TEXT NOT NULL,
            expected_delivery TEXT,
            FOREIGN KEY (sku) REFERENCES current_inventory(sku),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
        )
    """)

    conn.commit()
    logger.info("All tables created successfully.")


def populate_sales_history(conn: sqlite3.Connection) -> None:
    """Generate 12 months of daily sales data for SKU-001 through SKU-005."""
    cursor = conn.cursor()
    random.seed(42)

    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)

    # Base daily demand and seasonality multipliers per SKU
    base_demand = {
        "SKU-001": 8,
        "SKU-002": 25,
        "SKU-003": 5,
        "SKU-004": 4,
        "SKU-005": 10,
    }
    # Monthly seasonality factors: Jan-Feb post-holiday dip, summer steady,
    # Nov-Dec holiday shopping spike (1.4x-1.6x baseline)
    seasonality = {
        1: 0.8, 2: 0.75, 3: 0.85, 4: 0.9, 5: 1.0, 6: 1.05,
        7: 1.1, 8: 1.15, 9: 1.0, 10: 1.1, 11: 1.4, 12: 1.6,
    }

    rows = []
    current = start_date
    while current <= end_date:
        for sku, base in base_demand.items():
            month_factor = seasonality[current.month]
            # Add day-of-week effect (weekends slightly higher)
            dow_factor = 1.15 if current.weekday() >= 5 else 1.0
            daily_demand = max(
                0,
                int(base * month_factor * dow_factor + random.gauss(0, base * 0.2)),
            )
            price = SKU_CATALOG[sku]["unit_price"]
            rows.append((
                sku,
                current.strftime("%Y-%m-%d"),
                daily_demand,
                price,
                round(daily_demand * price, 2),
                random.choice(["online", "online", "online", "retail"]),
            ))
        current += timedelta(days=1)

    cursor.executemany(
        "INSERT INTO sales_history (sku, sale_date, quantity_sold, unit_price, total_revenue, channel) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    logger.info("Inserted %d sales history records.", len(rows))


def populate_current_inventory(conn: sqlite3.Connection) -> None:
    """Populate the current_inventory table with SKU data."""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for sku, info in SKU_CATALOG.items():
        cursor.execute(
            "INSERT OR REPLACE INTO current_inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sku,
                info["name"],
                info["category"],
                info["current_stock"],
                info["reorder_point"],
                info["safety_stock"],
                info["unit_cost"],
                info["unit_price"],
                info["warehouse_location"],
                now,
            ),
        )

    conn.commit()
    logger.info("Populated current_inventory for %d SKUs.", len(SKU_CATALOG))


def populate_suppliers(conn: sqlite3.Connection) -> None:
    """Populate the suppliers table."""
    cursor = conn.cursor()

    for sup in SUPPLIERS:
        cursor.execute(
            "INSERT OR REPLACE INTO suppliers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sup["id"],
                sup["name"],
                sup["contact_email"],
                sup["phone"],
                sup["lead_time_days"],
                sup["reliability_score"],
                sup["on_time_delivery_pct"],
                sup["defect_rate_pct"],
                sup["payment_terms"],
            ),
        )

    conn.commit()
    logger.info("Populated suppliers table with %d suppliers.", len(SUPPLIERS))


def main() -> None:
    """Create and populate the inventory database."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("Removed existing database at %s", DB_PATH)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        create_tables(conn)
        populate_sales_history(conn)
        populate_current_inventory(conn)
        populate_suppliers(conn)
        logger.info("Database setup complete at %s", DB_PATH)
    except Exception as e:
        logger.error("Database setup failed: %s", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
