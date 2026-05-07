# Retrieval Test Document
## Lab 2: Knowledge Engineering & Domain Grounding

This document demonstrates 3 test queries against the ChromaDB vector store,
including metadata filtering capabilities.

---

### Test 1: General Supplier Query (No Filter)

**Query**: "cheapest supplier for wireless headphones"

**Purpose**: Tests semantic search across all document types to find relevant
supplier pricing information.

**Expected Result**: Returns supplier catalog entries for SKU-001 from multiple
suppliers, ranked by semantic relevance to "cheapest" and "wireless headphones."

**Sample Output**:
```
[supplier_catalog] Supplier: GlobalElec Supply. Product: Wireless Headphones X1 (SKU: SKU-001). Unit price: $14.50...
[supplier_catalog] Supplier: TechDistributors Inc. Product: Wireless Headphones X1 (SKU: SKU-001). Unit price: $15.00...
[supplier_catalog] Supplier: PrimeParts Direct. Product: Wireless Headphones X1 (SKU: SKU-001). Unit price: $16.00...
```

---

### Test 2: Metadata-Filtered Query (Supplier Catalogs Only)

**Query**: "headphones price and lead time"
**Filter**: `{"doc_type": "supplier_catalog"}`

**Purpose**: Demonstrates metadata filtering — restricts search to only supplier
catalog documents, excluding sales history and inventory data.

**Expected Result**: Only supplier catalog chunks are returned, ensuring the
retrieval is precise and doesn't mix in irrelevant document types.

**Sample Output**:
```
[Supplier: TechDistributors Inc] ... Unit price: $15.00. Lead time: 7 days...
[Supplier: GlobalElec Supply] ... Unit price: $14.50. Lead time: 14 days...
[Supplier: PrimeParts Direct] ... Unit price: $16.00. Lead time: 3 days...
```

**Why This Matters**: In a real procurement workflow, the agent must be able to
query ONLY supplier data when comparing prices — mixing in sales history would
introduce noise and reduce decision quality.

---

### Test 3: Sales History Query with Metadata Filter

**Query**: "monthly sales trend for wireless headphones"
**Filter**: `{"doc_type": "sales_history"}`

**Purpose**: Tests retrieval of time-series sales summaries filtered by document
type, ensuring the agent can access historical demand data for forecasting.

**Expected Result**: Monthly aggregated sales summaries for SKU-001, showing
demand patterns across different months.

**Sample Output**:
```
[2025-11] Sales summary for Wireless Headphones X1 (SKU: SKU-001): Total units sold: 117. Returns: 5. Net demand: 112 units...
[2025-12] Sales summary for Wireless Headphones X1 (SKU: SKU-001): Total units sold: 100. Returns: 7. Net demand: 93 units...
[2025-01] Sales summary for Wireless Headphones X1 (SKU: SKU-001): Total units sold: 323. Returns: 16. Net demand: 307 units...
```

---

### Metadata Schema

Every chunk in the vector store is enriched with at least 3 searchable metadata tags:

| Metadata Key | Description | Example Values |
|-------------|-------------|----------------|
| `doc_type` | Type of source document | `supplier_catalog`, `sales_history`, `inventory_level`, `promotional_event` |
| `sku` | Product SKU identifier | `SKU-001`, `SKU-002`, `SKU-003` |
| `source_file` | Original data file name | `supplier_catalog_techdist.csv`, `sales_history.csv` |
| `supplier_name` | Supplier company name (catalogs only) | `TechDistributors Inc`, `GlobalElec Supply` |
| `category` | Product category | `Electronics`, `Accessories`, `Home Office` |
| `last_updated` | Timestamp of ingestion | `2026-03-12T10:30:00` |
