# Product Requirements Document (PRD)
## Dynamic Inventory Reorder Agent

---

## 1. Problem Statement

### The Bottleneck
Inventory management is a critical balancing act: too little stock leads to lost sales and customer dissatisfaction, while too much stock ties up capital and increases holding costs. Current manual processes fail because:

- **Reactive Ordering**: Procurement teams only reorder when stock hits critical levels, often too late to avoid stockouts
- **No Demand Forecasting**: Orders based on gut feeling or simple historical averages, ignoring seasonality, trends, and external factors
- **Supplier Blind Spots**: No visibility into supplier lead times, stock availability, or price changes until order is placed
- **Siloed Data**: Sales data, warehouse inventory, supplier catalogs, and market conditions exist in separate systems with no unified view
- **Manual Calculations**: Excel-based order quantity calculations prone to human error and outdated assumptions
- **Market Disruptions**: Unable to adjust for weather events, competitor actions, or supply chain disruptions

### Real-World Impact (Example: Electronics Retailer)
- **$2M in lost revenue annually** from stockouts during peak seasons (holiday, back-to-school)
- **$500K in excess inventory costs** due to over-ordering slow-moving items
- **30% of procurement team time** spent on manual data gathering instead of strategic sourcing
- **Average stockout duration: 12 days** because reorders only triggered when inventory hits zero

### Why This Requires an Agent (Not a Chatbot)
A simple dashboard or chatbot cannot solve this because the agent must:
- **Synthesize multi-modal data**: Sales trends, weather forecasts, supplier catalogs, competitor pricing, current inventory
- **Perform complex reasoning**: Demand forecasting, optimal order quantity calculation, supplier selection
- **Execute autonomous actions**: Generate purchase orders, send to suppliers via EDI/API, update ERP systems
- **Adapt in real-time**: Respond to sudden demand spikes, supplier outages, or price fluctuations
- **Optimize under constraints**: Balance cost, lead time, minimum order quantities, and storage capacity

---

## 2. User Personas

### Primary User: Jessica (Procurement Manager)
- **Role**: Manages inventory for 500+ SKUs at a mid-sized electronics retailer
- **Pain Points**:
  - Spends 20 hours/week manually reviewing inventory reports
  - Constantly firefighting stockouts instead of strategic planning
  - No easy way to factor in promotions, seasonality, or market events
  - Supplier negotiations hampered by lack of real-time alternatives
- **Goals**:
  - Reduce stockout incidents by 80%
  - Cut excess inventory holding costs by 40%
  - Spend <5 hours/week on routine reorder decisions
  - Get proactive alerts for supply chain risks

### Secondary User: Raj (Operations Director)
- **Role**: Oversees warehouse operations and inventory turnover
- **Pain Points**:
  - Warehouse space wasted on slow-moving inventory
  - No visibility into why certain items are over-ordered
  - Manual coordination between sales forecasts and procurement
- **Goals**:
  - Improve inventory turnover ratio from 4x to 6x annually
  - Maintain 95%+ in-stock rate for top 100 SKUs
  - Dashboard showing AI-driven reorder recommendations

### Tertiary User: Supplier (External Stakeholder)
- **Role**: Electronics distributor fulfilling orders
- **Pain Points**:
  - Receives last-minute rush orders with unrealistic lead times
  - No advance notice of bulk orders for capacity planning
- **Goals**:
  - Receive predictable, optimized order quantities
  - Automated order confirmation and fulfillment

---

## 3. Success Metrics

### Primary KPIs
| Metric | Current State | Target | Measurement Method |
|--------|--------------|--------|-------------------|
| **Stockout Rate** | 8% of orders | < 2% | % of customer orders unfulfilled due to no stock |
| **Excess Inventory Cost** | $500K/year | < $300K/year | Value of stock unsold after 90 days |
| **Forecast Accuracy** | 65% (MAPE) | 85% | Mean Absolute Percentage Error on 30-day demand |
| **Procurement Time Savings** | Baseline | 70% reduction | Hours spent on routine reorder tasks |

### Secondary KPIs
- **Average Inventory Turnover**: Target 6x/year (from current 4x)
- **Order Lead Time Variance**: Reduce by 50% through better supplier selection
- **Perfect Order Rate**: 90%+ (right item, right quantity, on time)
- **Cost Savings from Dynamic Pricing**: Capture supplier discounts/promotions worth 5%+ of procurement budget

### Success Criteria for Lab Demo
- Agent successfully forecasts demand for 3 products over 30 days
- Generates optimal reorder recommendations accounting for lead time and seasonality
- Demonstrates supplier comparison logic (price, availability, lead time)
- Executes simulated purchase order via API
- Shows exception handling (supplier stockout, sudden demand spike)

---

## 4. Agentic Use Case Definition

### Agent Capabilities

#### 📥 **PERCEIVE**: Multi-Source Data Extraction
The agent continuously monitors and extracts information from:

1. **Historical Sales Database (SQL)**
   - Transaction-level sales data (product, quantity, date, price)
   - Returns and refunds
   - Promotion/campaign performance

2. **Current Inventory System (ERP API)**
   - Real-time stock levels per SKU
   - Warehouse location and capacity
   - Reorder points and safety stock levels

3. **Supplier Catalogs (PDFs + APIs)**
   - Product availability and lead times
   - Pricing tiers (volume discounts)
   - Minimum order quantities (MOQs)
   - Terms and conditions

4. **External Market Data**
   - Weather forecasts (impacts seasonal items like winter gear, fans)
   - Economic indicators (consumer confidence, unemployment)
   - Competitor pricing (web scraping or third-party APIs)
   - Industry reports (market trends, supply chain disruptions)

5. **Event Calendar**
   - Promotional campaigns (Black Friday, back-to-school)
   - Local events (sports games, concerts driving merchandise)
   - Shipping holidays (Chinese New Year affecting supplier capacity)

#### 🧠 **REASON**: Multi-Step Planning with LangGraph
The agent uses a sophisticated state machine to optimize inventory decisions:

**State Graph Flow**:
```
[Daily Inventory Scan Triggered]
    ↓
[Retrieve Current Stock Levels] → Query ERP for all SKUs
    ↓
[Identify Low Stock Items] → Filter SKUs below reorder point
    ↓
FOR EACH Low Stock SKU:
    ↓
[Demand Forecasting Node]
    ├→ Fetch 12 months sales history
    ├→ Check upcoming promotions/events
    ├→ Query weather API (seasonal items)
    └→ Generate 30-day demand forecast (ML model)
    ↓
[Calculate Optimal Order Quantity]
    ├→ Consider lead time
    ├→ Account for safety stock
    ├→ Optimize for EOQ (Economic Order Quantity)
    └→ Apply warehouse capacity constraints
    ↓
[Supplier Selection Node]
    ├→ Query all approved suppliers for SKU
    ├→ Compare: price, availability, lead time, reliability
    ├→ Check for volume discounts
    └→ Select optimal supplier (multi-criteria decision)
    ↓
[Decision Gate]
    ├─→ [Routine Order] → Auto-approve if < $10K
    └─→ [High-Value Order] → Flag for human review
    ↓
[Generate Purchase Order]
    ├→ Create PO document with line items
    ├→ Calculate total cost
    └→ Set expected delivery date
    ↓
[Execute Order]
    ├→ Send PO to supplier (Email/EDI/API)
    ├→ Update ERP with expected receipt
    └→ Schedule follow-up check
    ↓
[Monitor Delivery]
    ├→ Track shipment status
    └→ Alert if delayed beyond 2 days
```

**Decision Logic Examples**:
- If `demand_forecast_next_30d > current_stock + pending_orders` → Trigger reorder
- If `supplier_A_price < supplier_B_price * 0.95` AND `lead_time_diff < 3_days` → Choose supplier A
- If `upcoming_promotion in 7_days` → Increase order quantity by 40%
- If `weather_forecast == "cold_snap"` AND `product_category == "winter_apparel"` → Expedite order
- If `supplier_stock_status == "low"` → Check alternative suppliers immediately

#### ⚡ **EXECUTE**: External Tool Invocation
The agent calls Python functions to interact with the world:

1. **`get_sales_data(sku, start_date, end_date)`**
   - Queries PostgreSQL for historical transaction data
   - Returns: daily sales, returns, net demand

2. **`get_current_inventory(sku)`**
   - Calls ERP REST API for real-time stock levels
   - Returns: on-hand qty, reserved qty, available qty

3. **`forecast_demand(sku, historical_data, external_factors)`**
   - ML model (Prophet/ARIMA) for time series forecasting
   - Returns: 30-day demand prediction with confidence intervals

4. **`query_supplier_catalog(sku, supplier_id)`**
   - Parses supplier PDF catalogs (cached in vector DB) or calls API
   - Returns: price, MOQ, lead time, stock status

5. **`get_weather_forecast(location, days_ahead)`**
   - External weather API (OpenWeatherMap)
   - Returns: temperature, precipitation, severe weather alerts

6. **`calculate_order_quantity(forecast, lead_time, safety_stock)`**
   - Economic Order Quantity (EOQ) algorithm
   - Returns: optimal order qty, reorder point

7. **`generate_purchase_order(sku, quantity, supplier, price)`**
   - Creates PO document (JSON → PDF)
   - Returns: PO number, total cost, line items

8. **`send_po_to_supplier(po_document, supplier_email, api_endpoint)`**
   - Email with PDF attachment OR API call (EDI format)
   - Returns: confirmation status

9. **`update_erp_system(sku, expected_qty, eta)`**
   - Updates inventory system with incoming stock
   - Returns: success/failure

10. **`get_competitor_price(sku, competitors_list)`**
    - Web scraping or third-party pricing API
    - Returns: competitor prices for benchmarking

---

## 5. System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACES                          │
├─────────────────────────────────────────────────────────────┤
│  Procurement Dashboard  │  Alerts Panel  │  Analytics       │
└────────┬────────────────────────┬────────────┬──────────────┘
         │                        │            │
         ▼                        ▼            ▼
┌─────────────────────────────────────────────────────────────┐
│              LANGGRAPH ORCHESTRATION LAYER                  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │         STATE GRAPH (Inventory Controller)           │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  • Daily Inventory Scanner                           │  │
│  │  • Demand Forecasting Orchestrator                   │  │
│  │  • Supplier Selection Engine                         │  │
│  │  • Order Approval Router (Auto/Manual)               │  │
│  │  • Delivery Monitor                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              AI REASONING NODES                      │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  • Demand Forecasting Model (ML)                     │  │
│  │  • Supplier Evaluator (Multi-criteria LLM)           │  │
│  │  • Market Context Analyzer (RAG on reports)          │  │
│  │  • Exception Handler (Edge case reasoning)           │  │
│  └──────────────────────────────────────────────────────┘  │
└────────┬────────────────────────────────────┬───────────────┘
         │                                    │
         ▼                                    ▼
┌──────────────────────┐          ┌──────────────────────────┐
│   TOOL LAYER         │          │   MEMORY LAYER           │
├──────────────────────┤          ├──────────────────────────┤
│ • ERP API            │          │ • Inventory State        │
│ • SQL Database       │          │ • Order History          │
│ • Weather API        │          │ • Supplier Performance   │
│ • Supplier APIs/EDI  │          │ • Forecast Cache         │
│ • Email/Slack        │          │ • Decision Logs          │
│ • ML Model Server    │          └──────────────────────────┘
│ • PDF Generator      │
└──────────┬───────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│                   DATA SOURCES                              │
├─────────────────────────────────────────────────────────────┤
│  Sales DB  │  ERP  │  Supplier Catalogs  │  Weather API    │
│  Market Reports  │  Event Calendar  │  Competitor Data     │
└─────────────────────────────────────────────────────────────┘
```

### LangGraph Workflow Detail

**Node Types**:
1. **Trigger Node**: Scheduled daily scan OR manual trigger from dashboard
2. **Inventory Retrieval Node**: Queries ERP for current stock levels
3. **Filter Node**: Identifies SKUs below reorder point
4. **Forecasting Node**: ML-based demand prediction with external factors
5. **Supplier Query Node**: Retrieves current pricing/availability from all suppliers
6. **Optimization Node**: Calculates optimal order quantity (EOQ model)
7. **Decision Node**: Auto-approve vs flag for human review
8. **Action Node**: Generates and sends purchase order
9. **Monitoring Node**: Tracks delivery status post-order

**State Schema**:
```python
{
  "scan_id": "SCAN-2024-03-10",
  "timestamp": "2024-03-10T06:00:00Z",
  "low_stock_skus": ["SKU-001", "SKU-045", "SKU-127"],
  "processing_sku": "SKU-001",
  "sku_details": {
    "sku": "SKU-001",
    "name": "Wireless Headphones X1",
    "current_stock": 45,
    "reorder_point": 100,
    "forecasted_demand_30d": 250,
    "optimal_order_qty": 300,
    "selected_supplier": "TechDistributors Inc",
    "order_cost": 4500.00,
    "eta": "2024-03-20"
  },
  "orders_generated": [
    {
      "po_number": "PO-2024-0310-001",
      "status": "sent",
      "total": 4500.00
    }
  ],
  "approval_required": false
}
```

---

## 6. Tool & Data Inventory

### Knowledge Sources (PERCEIVE)

| Source | Format | Purpose | Access Method |
|--------|--------|---------|---------------|
| **Sales Transaction DB** | PostgreSQL | Historical demand data | SQL queries |
| **Inventory System (ERP)** | REST API | Real-time stock levels | API calls |
| **Supplier Catalogs** | PDF/Excel | Product pricing, MOQs, lead times | PDF parsing + Vector DB |
| **Weather API** | JSON | Forecast for seasonal demand | REST API (OpenWeatherMap) |
| **Market Reports** | PDF/Web | Industry trends, disruptions | RAG pipeline |
| **Promotional Calendar** | Google Sheets | Upcoming campaigns | Sheets API |
| **Supplier Performance DB** | PostgreSQL | Historical delivery times, quality | SQL queries |

### Action Tools (EXECUTE)

| Tool Function | Parameters | External System | Purpose |
|---------------|------------|-----------------|---------|
| `get_sales_data()` | sku, start_date, end_date | PostgreSQL | Historical demand |
| `get_current_inventory()` | sku | ERP API | Real-time stock |
| `forecast_demand()` | sku, history, events | ML Model (Prophet) | 30-day prediction |
| `query_supplier_catalog()` | sku, supplier_id | PDF/API | Pricing & availability |
| `get_weather_forecast()` | location, days | OpenWeatherMap | Seasonal factors |
| `calculate_order_qty()` | forecast, lead_time | Python EOQ algorithm | Optimization |
| `generate_purchase_order()` | sku, qty, supplier | Jinja2 → PDF | PO creation |
| `send_po_to_supplier()` | po_doc, email/api | Email/EDI | Order transmission |
| `update_erp_system()` | sku, qty, eta | ERP API | Inventory update |
| `get_competitor_price()` | sku, competitors | Web scraping | Price benchmarking |
| `send_alert()` | message, urgency | Slack API | Notifications |

---

## 7. Implementation Roadmap

### Phase 1: MVP (Lab Submission)
- [ ] Basic state graph with 7 core nodes
- [ ] Mock sales database with 12 months of data (SQLite)
- [ ] Simple demand forecasting (moving average or Prophet)
- [ ] Supplier catalog parsing (2-3 PDFs)
- [ ] Weather API integration (OpenWeatherMap free tier)
- [ ] PO generation (PDF output, no actual sending)
- [ ] Demonstrate full flow for 2-3 SKUs

### Phase 2: Production-Ready
- [ ] Advanced ML forecasting (LSTM, ensemble models)
- [ ] Real ERP integration (SAP, Oracle, NetSuite)
- [ ] EDI/API connections to suppliers
- [ ] Multi-warehouse optimization
- [ ] Real-time delivery tracking
- [ ] A/B testing framework for forecast accuracy

---

## 8. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Forecast inaccuracy** | High - stockouts or overstock | Human review for high-value orders, confidence thresholds |
| **Supplier API downtime** | Medium - delayed orders | Fallback to email/manual, cache supplier data |
| **Over-automation leading to loss of expertise** | Medium - blind reliance on AI | Dashboard showing AI reasoning, override capabilities |
| **Data quality issues** | High - garbage in, garbage out | Data validation layer, anomaly detection |
| **Price volatility** | Medium - unexpected cost spikes | Set approval thresholds for large cost increases |

---

## 9. Advanced Features (Differentiation)

### Multi-Criteria Supplier Selection
Not just cheapest price, but weighted scoring:
- **Price**: 40%
- **Lead Time**: 25%
- **Reliability** (on-time delivery %): 20%
- **Quality** (defect rate): 15%

### Scenario Planning
"What-if" analysis:
- "If supplier X has a 2-week delay, what's the impact?"
- "If we run a 20% off promotion, do we have enough stock?"

### Sustainability Tracking
- Carbon footprint of shipping options
- Supplier ESG scores
- Local sourcing preferences

---

## 10. Technical Stack Recommendation

- **LangGraph**: Workflow orchestration
- **LangChain**: LLM integration, RAG for market reports
- **OpenAI GPT-4**: Supplier evaluation, exception handling
- **Prophet/ARIMA**: Time series forecasting
- **PostgreSQL**: Sales and supplier performance data
- **ChromaDB**: Vector storage for supplier catalogs
- **FastAPI**: REST API for dashboard
- **Celery + Redis**: Scheduled daily scans
- **Docker**: Containerization

---

## Appendix: Sample Interaction Flow

**Scenario**: Wireless Headphones (SKU-001) inventory drops below reorder point.

1. **Day 1, 6:00 AM**: Daily scan triggered
   - Agent queries ERP: Current stock = 45 units
   - Reorder point = 100 units → Flagged for reorder

2. **Day 1, 6:05 AM**: Demand forecasting
   - Fetches 12 months sales data: avg 8 units/day
   - Checks promotional calendar: Black Friday in 30 days (expect 3x spike)
   - Weather API: No seasonal impact (electronics)
   - Forecast: 250 units needed over next 30 days

3. **Day 1, 6:10 AM**: Supplier selection
   - Queries 3 approved suppliers:
     - **Supplier A**: $15/unit, 7-day lead time, 95% reliability
     - **Supplier B**: $14.50/unit, 14-day lead time, 88% reliability
     - **Supplier C**: $16/unit, 3-day lead time, 99% reliability
   - Agent selects Supplier A (best price-reliability balance)

4. **Day 1, 6:15 AM**: Order optimization
   - EOQ calculation: Optimal order = 300 units (accounts for Black Friday)
   - Total cost: $4,500
   - Auto-approved (below $10K threshold)

5. **Day 1, 6:20 AM**: PO generation and sending
   - Creates PO-2024-0310-001
   - Sends PDF to supplier via email
   - Updates ERP: Expected receipt 250 units on March 17
   - Slack notification to Jessica: "Auto-ordered 300 units SKU-001 from Supplier A ($4,500)"

6. **Day 8**: Delivery monitoring
   - Tracking shows delay → Agent sends alert
   - Jessica reviews, contacts supplier

This demonstrates autonomous multi-step reasoning, data synthesis from 5+ sources, and execution without human intervention for routine decisions.
