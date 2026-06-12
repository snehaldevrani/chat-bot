# CityPark Chatbot — Stage 1: RAG System and Chatbot

## Overview

Stage 1 establishes the foundation of the CityPark parking chatbot. It implements a Retrieval-Augmented Generation (RAG) pipeline that lets users ask questions about parking facilities and interactively submit reservation requests. A two-layer guardrails system protects against prompt injection and prevents PII leakage in responses. An evaluation harness measures retrieval accuracy and response latency.

## Architecture

```
User Input
    │
    ▼
┌─────────────────────────┐
│   Input Guardrail        │  ← Prompt injection detection (regex)
└────────────┬────────────┘
             │
    ┌────────▼────────┐
    │ Intent Detection │  ← "info_query" or "reservation"
    └───┬─────────┬───┘
        │         │
   ┌────▼───┐  ┌──▼──────────┐
   │  RAG   │  │  Reservation │
   │  Node  │  │  Node        │  ← 7-step interactive collection
   └────┬───┘  └──────┬───────┘
        │             │
        └──────┬──────┘
               ▼
   ┌───────────────────────┐
   │   Output Guardrail    │  ← Presidio PII anonymizer
   └───────────────────────┘
               │
               ▼
          Response
```

**Key components:**
- **RAG Node**: Retrieves from ChromaDB, injects live DB context (availability, pricing, hours), generates response via Azure OpenAI (GPT-4o).
- **Semantic Cache**: Redis-backed (in-memory fallback) with cosine similarity threshold 0.92 and 1-hour TTL, reducing redundant LLM calls.
- **Database**: SQLite via SQLAlchemy — 57 parking spaces across 4 levels, 4 pricing tiers, 7-day operating hours.
- **Evaluation**: Recall@K, Precision@K, and latency measured against a 20-question test dataset.

## Features Implemented

- Interactive RAG chatbot answering questions on parking info, pricing, location, hours, availability
- 7-step reservation collection: name → surname → car number → start datetime → end datetime → space type → confirmation
- Field validation with regex patterns and datetime normalization
- Two-layer guardrails: prompt injection detection + Presidio PII anonymization
- Semantic cache with Redis fallback
- RAG evaluation: Recall@K, Precision@K, latency metrics
- Static documents in ChromaDB; dynamic data (availability, pricing, hours) in SQLite — updated live at query time
- Reservations persisted in SQLite with `collected` status (no admin approval in this stage)

## Setup Instructions

### Prerequisites

- Python 3.11+
- Access to EPAM AI Dial or Azure OpenAI (for embeddings and LLM)
- Redis (optional — in-memory fallback is used if unavailable)
- spaCy model `en_core_web_lg`

### Steps

```bash
# 1. Clone / navigate to stage1 directory
cd releases/stage1

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download the spaCy model (required by Presidio)
python -m spacy download en_core_web_lg

# 5. Configure environment variables
cp ../../.env .env          # or create .env manually with the variables below
```

**Required `.env` variables:**

```env
DIAL_API_KEY=your_api_key
DIAL_ENDPOINT=https://your-dial-endpoint/openai
DIAL_LLM_DEPLOYMENT=gpt-4o
DIAL_EMBEDDING_DEPLOYMENT=text-embedding-3-small-1

# Optional
REDIS_URL=redis://localhost:6379
```

## Running the Application

```bash
# First-time setup: seed the database and build the vector store
python main.py --setup

# Start the chatbot
python main.py

# Run RAG evaluation and print metrics
python main.py --evaluate
```

Example session:
```
You: What are your parking rates?
Bot: Regular spaces cost $3/hr, EV charging $5/hr, VIP $8/hr, handicapped $2/hr...

You: I'd like to reserve a spot
Bot: I'd be happy to help with a reservation. What is your first name?
```

## Running Tests

```bash
cd releases/stage1
pytest -v
```

**Test file:** `tests/test_stage1_snapshot.py`

| Test | Description |
|------|-------------|
| `test_guardrail_blocks_prompt_injection` | Verifies injection attempts are blocked |
| `test_reservation_collection_stops_without_admin` | Confirms reservation ends at `done` with no admin escalation |
| `test_rag_node_uses_vectorstore_and_live_context` | Verifies RAG retrieves docs and injects live data |
| `test_stage1_has_no_admin_or_mcp_modules` | Confirms no Stage 2/3 code is present |

## Assignment Requirements Satisfied

| Requirement | Status |
|-------------|--------|
| RAG architecture using LangChain | Done — LangChain chains, ChromaDB, AzureOpenAI |
| Vector database for information storage | Done — ChromaDB with text-embedding-3-small-1 |
| Optional: dynamic/static data split | Done — static in ChromaDB, dynamic in SQLite |
| Provide information to users | Done — pricing, availability, hours, location, FAQ |
| Collect user inputs for reservations | Done — 7-step interactive collection |
| Guardrails for sensitive data protection | Done — injection detection + Presidio PII anonymizer |
| RAG evaluation (Recall@K, Precision@K, latency) | Done — `src/evaluation/metrics.py` |
| Automated tests (pytest) | Done — 40 tests across 5 test files (per-module coverage) |
| CI/CD | Done — `.github/workflows/ci.yml` at repo root |

## Project Structure

```
releases/stage1/
├── main.py                        # Entry point (--setup, --evaluate, chat modes)
├── requirements.txt
├── pytest.ini
├── conftest.py
├── data/
│   └── static/                    # 8 static documents ingested into ChromaDB
│       ├── parking_overview.txt
│       ├── location_directions.txt
│       ├── levels_layout.txt
│       ├── features_amenities.txt
│       ├── rules_regulations.txt
│       ├── faq.txt
│       ├── booking_process.txt
│       └── contact_info.txt
├── src/
│   ├── config.py                  # Environment variables and constants
│   ├── agents/
│   │   ├── state.py               # TypedDict state schema
│   │   └── nodes.py               # Pipeline nodes: guardrail, intent, RAG, reservation, output
│   ├── rag/
│   │   ├── loader.py              # Document loading and chunking
│   │   ├── vectorstore.py         # ChromaDB + AzureOpenAI embeddings
│   │   ├── retriever.py           # Similarity-search retriever (k=4)
│   │   └── semantic_cache.py      # Redis/in-memory semantic cache
│   ├── database/
│   │   ├── models.py              # SQLAlchemy ORM: ParkingSpace, Pricing, WorkingHours, Reservation
│   │   ├── seed.py                # Database seeding (57 spaces, 4 pricing tiers, 7-day hours)
│   │   └── queries.py             # Availability, pricing, hours queries; create_reservation
│   ├── guardrails/
│   │   └── filters.py             # InputFilter (injection), OutputFilter (Presidio PII)
│   └── evaluation/
│       ├── metrics.py             # recall_at_k, precision_at_k, measure_latency, run_evaluation
│       └── test_dataset.json      # 20 annotated Q&A pairs
└── tests/
    ├── test_stage1_snapshot.py
    ├── test_database.py
    ├── test_evaluation.py
    ├── test_guardrails.py
    └── test_rag.py
```

## Future Improvements

- Introduce a proper LangChain agent (e.g., `create_react_agent`) for more flexible tool use
- Add LangGraph orchestration (implemented in Stage 4)
- Support for multiple concurrent users via thread-based state management
