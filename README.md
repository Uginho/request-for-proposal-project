# Automated RFP System: A Single, Automated System That Runs an Entire Procurement Workflow End-to-End

This system automates the entire restaurant procurement lifecycle—from parsing/cleaning raw PDF metadata from the menu into structured recipes broken down by ingredient—to programmatically dispatching tailored RFP emails to local distributors.

Built for Pablo y Pablo, a Latin restaurant in Seattle, the engine replaces manual data entry with an artificial intelligent, agentic ETL pipeline.

**Pablo y Pablo Lunch/Dinner Menu Source:** [Pablo y Pablo Dinner Menu](https://static1.squarespace.com/static/662702fb8ca58656a0118d85/t/6946e46e7ee75d2994ce77a0/1766253678238/Pablo_DINNER_1218.pdf)

**Walkthrough:** [Screen Recording]

---

## System Architecture & Logic

The system follows a strict Medallion Architecture to handle the "messy" reality of culinary and agricultural data.

| Stage | Process | Data Layer |
|---|---|---|
| **Step 1: Parse** | pdfplumber + Claude Haiku extract structured ingredients & quantities | Bronze: Unstructured PDF → JSON |
| **Step 2: Price** | USDA AMS API mapping with dynamic regex normalization to Price/lb | Silver: Normalized Market Benchmarks |
| **Step 3: Route** | Curated Seattle distributor matching via "Specialty" categorization | Gold: Verified Supplier Directory |
| **Step 4: Execute** | smtplib triggers category-specific RFPs with quantity & deadline tracking | Output: Live Procurement Logs |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Core | Python 3.13 |
| UI | Streamlit (Lightweight pipeline visualization) |
| Database | SQLite with foreign key enforcement (Canonical schema) |
| Intelligence | Claude Haiku (claude-haiku-4-5-20251001) |
| Pricing API | USDA AMS Market News (Los Angeles Terminal proxy) |
| Email | Gmail SMTP (Tailored routing based on distributor specialty) |

---

## Engineering Decisions & Pain Point Mitigation

The core challenge of this project was the "Entity Matching" gap between a kitchen menu and federal market data.

**1. The Normalization Engine (Step 2)**

USDA package sizes vary wildly (e.g., 25lb boxes vs. 100lb sacks). Was able to implement a dynamic regex-based normalization layer to extract numeric weights and convert them to a standard Price/lb benchmark — simple business logic.

**2. High-Performance Parallelization**

To overcome API slowness, was able to implement parallel report fetching using `ThreadPoolExecutor`. This reduced the USDA data ingestion time from ~120 seconds to ~15 seconds, significantly improving the UX.

**3. Intelligent Routing (Step 4)**

Instead of a "spray and pray" email approach, was able to enable the system to use a specialty-to-category routing logic. Seafood distributors only receive seafood RFPs, while Broadline suppliers receive the full list, mimicking real-world professional procurement.

---

## Installation & Setup

```bash
# 1. Environment Setup
git clone https://github.com/YOUR_USERNAME/pathway-rfp.git
cd pathway-rfp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

```bash
# 2. Configuration
# Create a .env file with:
ANTHROPIC_API_KEY=your-key
USDA_API_KEY=your-key
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
```

```bash
# 3. Launch Pipeline
streamlit run app.py
```

---

## Testing

```bash
pytest tests/
```

Validated with 70 passing unit tests covering idempotency, LLM parsing, and DB persistence.
