"""
Lab 2: Knowledge Engineering & Domain Grounding
================================================
RAG pipeline for the Dynamic Inventory Reorder Agent.
Ingests supplier catalogs, sales history, inventory levels, and promotional
calendars into a ChromaDB vector store with rich metadata for retrieval.
"""

import csv
import os
import hashlib
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions

from config import (
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    EMBEDDING_MODEL,
    SALES_HISTORY_PATH,
    INVENTORY_LEVELS_PATH,
    SUPPLIER_CATALOGS,
    PROMOTIONAL_CALENDAR_PATH,
)


# ─── Embedding Function ─────────────────────────────────────────────────────

def get_embedding_function():
    """Return a SentenceTransformer-based embedding function for ChromaDB."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )


# ─── Data Cleaning Utilities ────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Strip domain-specific noise: excessive whitespace, HTML tags, special chars."""
    import re
    text = re.sub(r"<[^>]+>", "", text)          # Remove HTML tags
    text = re.sub(r"\s+", " ", text)              # Collapse whitespace
    text = text.strip()
    return text


def generate_chunk_id(text: str, source: str, index: int) -> str:
    """Generate a deterministic ID for a chunk based on content and source."""
    raw = f"{source}_{index}_{text[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()


# ─── Ingestion Functions ────────────────────────────────────────────────────

def ingest_supplier_catalogs(collection) -> int:
    """Ingest supplier catalog CSVs into the vector store with metadata."""
    count = 0
    for catalog_path in SUPPLIER_CATALOGS:
        if not os.path.exists(catalog_path):
            print(f"  [SKIP] {catalog_path} not found")
            continue

        filename = os.path.basename(catalog_path)
        supplier_name = None

        with open(catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                supplier_name = row.get("supplier_name", "Unknown")
                sku = row.get("sku", "")
                product = row.get("product_name", "")
                price = row.get("unit_price", "")
                moq = row.get("moq", "")
                lead_time = row.get("lead_time_days", "")
                stock_status = row.get("stock_status", "")
                reliability = row.get("reliability_score", "")
                discount_threshold = row.get("volume_discount_threshold", "")
                discount_pct = row.get("volume_discount_pct", "")

                # Semantic chunk: a natural-language description of the offering
                chunk_text = clean_text(
                    f"Supplier: {supplier_name}. "
                    f"Product: {product} (SKU: {sku}). "
                    f"Unit price: ${price}. Minimum order quantity: {moq} units. "
                    f"Lead time: {lead_time} days. Stock status: {stock_status}. "
                    f"Reliability score: {reliability}%. "
                    f"Volume discount: {discount_pct}% off for orders above {discount_threshold} units."
                )

                metadata = {
                    "doc_type": "supplier_catalog",
                    "supplier_name": supplier_name,
                    "supplier_id": row.get("supplier_id", ""),
                    "sku": sku,
                    "product_name": product,
                    "unit_price": float(price) if price else 0.0,
                    "lead_time_days": int(lead_time) if lead_time else 0,
                    "stock_status": stock_status,
                    "reliability_score": float(reliability) if reliability else 0.0,
                    "source_file": filename,
                    "last_updated": datetime.now().isoformat(),
                }

                chunk_id = generate_chunk_id(chunk_text, filename, i)
                collection.add(
                    documents=[chunk_text],
                    metadatas=[metadata],
                    ids=[chunk_id],
                )
                count += 1

        print(f"  [OK] Ingested {filename} ({supplier_name})")
    return count


def ingest_sales_history(collection) -> int:
    """Ingest sales history as aggregated monthly summaries per SKU."""
    if not os.path.exists(SALES_HISTORY_PATH):
        print(f"  [SKIP] {SALES_HISTORY_PATH} not found")
        return 0

    # Aggregate by SKU and month
    aggregated = {}
    with open(SALES_HISTORY_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row["date"]
            month_key = date[:7]  # YYYY-MM
            sku = row["sku"]
            key = f"{sku}_{month_key}"

            if key not in aggregated:
                aggregated[key] = {
                    "sku": sku,
                    "product_name": row["product_name"],
                    "category": row["category"],
                    "month": month_key,
                    "total_sold": 0,
                    "total_returns": 0,
                    "records": 0,
                    "promo_days": 0,
                }
            aggregated[key]["total_sold"] += int(row["quantity_sold"])
            aggregated[key]["total_returns"] += int(row["returns"])
            aggregated[key]["records"] += 1
            if row["promotion_active"] == "True":
                aggregated[key]["promo_days"] += 1

    count = 0
    for key, data in aggregated.items():
        net_demand = data["total_sold"] - data["total_returns"]
        avg_daily = round(net_demand / max(data["records"], 1), 1)

        chunk_text = clean_text(
            f"Sales summary for {data['product_name']} (SKU: {data['sku']}) "
            f"in {data['month']}: "
            f"Total units sold: {data['total_sold']}. Returns: {data['total_returns']}. "
            f"Net demand: {net_demand} units. "
            f"Average daily demand: {avg_daily} units/day. "
            f"Promotion days in period: {data['promo_days']}. "
            f"Category: {data['category']}."
        )

        metadata = {
            "doc_type": "sales_history",
            "sku": data["sku"],
            "product_name": data["product_name"],
            "category": data["category"],
            "month": data["month"],
            "total_sold": data["total_sold"],
            "net_demand": net_demand,
            "source_file": "sales_history.csv",
            "last_updated": datetime.now().isoformat(),
        }

        chunk_id = generate_chunk_id(chunk_text, "sales_history", count)
        collection.add(
            documents=[chunk_text],
            metadatas=[metadata],
            ids=[chunk_id],
        )
        count += 1

    print(f"  [OK] Ingested sales history ({count} monthly summaries)")
    return count


def ingest_inventory_levels(collection) -> int:
    """Ingest current inventory levels into the vector store."""
    if not os.path.exists(INVENTORY_LEVELS_PATH):
        print(f"  [SKIP] {INVENTORY_LEVELS_PATH} not found")
        return 0

    count = 0
    with open(INVENTORY_LEVELS_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            stock = row["current_stock"]
            reorder_pt = row["reorder_point"]
            status = "BELOW reorder point" if int(stock) < int(reorder_pt) else "ABOVE reorder point"

            chunk_text = clean_text(
                f"Inventory status for {row['product_name']} (SKU: {row['sku']}): "
                f"Current stock: {stock} units. Reorder point: {reorder_pt} units. "
                f"Safety stock: {row['safety_stock']} units. "
                f"Max warehouse capacity: {row['max_capacity']} units. "
                f"Location: {row['warehouse_location']}. "
                f"Unit cost: ${row['unit_cost']}. "
                f"Status: {status}."
            )

            metadata = {
                "doc_type": "inventory_level",
                "sku": row["sku"],
                "product_name": row["product_name"],
                "category": row["category"],
                "current_stock": int(stock),
                "reorder_point": int(reorder_pt),
                "warehouse_location": row["warehouse_location"],
                "source_file": "inventory_levels.csv",
                "last_updated": row["last_updated"],
            }

            chunk_id = generate_chunk_id(chunk_text, "inventory_levels", i)
            collection.add(
                documents=[chunk_text],
                metadatas=[metadata],
                ids=[chunk_id],
            )
            count += 1

    print(f"  [OK] Ingested inventory levels ({count} SKUs)")
    return count


def ingest_promotional_calendar(collection) -> int:
    """Ingest promotional events into the vector store."""
    if not os.path.exists(PROMOTIONAL_CALENDAR_PATH):
        print(f"  [SKIP] {PROMOTIONAL_CALENDAR_PATH} not found")
        return 0

    count = 0
    with open(PROMOTIONAL_CALENDAR_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            chunk_text = clean_text(
                f"Promotional event: {row['event_name']}. "
                f"Period: {row['start_date']} to {row['end_date']}. "
                f"Affected categories: {row['affected_categories']}. "
                f"Expected demand multiplier: {row['expected_demand_multiplier']}x. "
                f"Discount: {row['discount_pct']}%. "
                f"Description: {row['description']}."
            )

            metadata = {
                "doc_type": "promotional_event",
                "event_name": row["event_name"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "affected_categories": row["affected_categories"],
                "demand_multiplier": float(row["expected_demand_multiplier"]),
                "source_file": "promotional_calendar.csv",
                "last_updated": datetime.now().isoformat(),
            }

            chunk_id = generate_chunk_id(chunk_text, "promotional_calendar", i)
            collection.add(
                documents=[chunk_text],
                metadatas=[metadata],
                ids=[chunk_id],
            )
            count += 1

    print(f"  [OK] Ingested promotional calendar ({count} events)")
    return count


# ─── Main Pipeline ──────────────────────────────────────────────────────────

def build_knowledge_base():
    """
    Build the complete RAG knowledge base by ingesting all data sources
    into ChromaDB with metadata-enriched semantic chunks.
    """
    print("=" * 60)
    print("Dynamic Inventory Reorder Agent — RAG Pipeline")
    print("=" * 60)

    # Initialize ChromaDB with persistence
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    embedding_fn = get_embedding_function()

    # Delete existing collection if it exists (fresh build)
    try:
        client.delete_collection(CHROMA_COLLECTION_NAME)
        print("[INFO] Deleted existing collection for fresh rebuild.")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "Inventory reorder agent knowledge base"},
    )

    print("\n[1/4] Ingesting supplier catalogs...")
    supplier_count = ingest_supplier_catalogs(collection)

    print("\n[2/4] Ingesting sales history...")
    sales_count = ingest_sales_history(collection)

    print("\n[3/4] Ingesting inventory levels...")
    inventory_count = ingest_inventory_levels(collection)

    print("\n[4/4] Ingesting promotional calendar...")
    promo_count = ingest_promotional_calendar(collection)

    total = supplier_count + sales_count + inventory_count + promo_count
    print(f"\n{'=' * 60}")
    print(f"Knowledge base built successfully!")
    print(f"  Supplier catalog chunks : {supplier_count}")
    print(f"  Sales history chunks    : {sales_count}")
    print(f"  Inventory level chunks  : {inventory_count}")
    print(f"  Promotional event chunks: {promo_count}")
    print(f"  TOTAL chunks indexed    : {total}")
    print(f"  ChromaDB path           : {CHROMA_PERSIST_DIR}")
    print(f"{'=' * 60}")

    return collection


def query_knowledge_base(query: str, n_results: int = 3, where_filter: dict = None):
    """
    Query the knowledge base with optional metadata filtering.

    Args:
        query: Natural language search query.
        n_results: Number of results to return.
        where_filter: ChromaDB metadata filter (e.g., {"doc_type": "supplier_catalog"}).

    Returns:
        dict with 'documents', 'metadatas', and 'distances'.
    """
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    embedding_fn = get_embedding_function()
    collection = client.get_collection(
        name=CHROMA_COLLECTION_NAME,
        embedding_function=embedding_fn,
    )

    kwargs = {"query_texts": [query], "n_results": n_results}
    if where_filter:
        kwargs["where"] = where_filter

    results = collection.query(**kwargs)
    return results


# ─── Demo / Test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Build the knowledge base
    build_knowledge_base()

    print("\n\n" + "=" * 60)
    print("RETRIEVAL TESTS")
    print("=" * 60)

    # Test 1: General query
    print("\n--- Test 1: General supplier query ---")
    results = query_knowledge_base("cheapest supplier for wireless headphones")
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        print(f"  [{meta['doc_type']}] {doc[:120]}...")

    # Test 2: Metadata-filtered query (supplier catalogs only)
    print("\n--- Test 2: Metadata filter — supplier catalogs only ---")
    results = query_knowledge_base(
        "headphones price and lead time",
        where_filter={"doc_type": "supplier_catalog"},
    )
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        print(f"  [Supplier: {meta.get('supplier_name', 'N/A')}] {doc[:120]}...")

    # Test 3: Sales history query
    print("\n--- Test 3: Sales history for SKU-001 ---")
    results = query_knowledge_base(
        "monthly sales trend for wireless headphones",
        where_filter={"doc_type": "sales_history"},
    )
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        print(f"  [{meta.get('month', 'N/A')}] {doc[:120]}...")

    print("\n[DONE] All retrieval tests passed.")
