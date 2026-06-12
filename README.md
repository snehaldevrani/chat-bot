# CityPark Chatbot — Stage 4: Full LangGraph Orchestration

## Overview

CityPark Chatbot is an intelligent parking reservation assistant built in four stages. Stage 4 orchestrates all previous components — RAG chatbot (Stage 1), human-in-the-loop admin approval (Stage 2), and MCP persistence (Stage 3) — into a unified LangGraph pipeline. The system uses a compiled StateGraph with MemorySaver checkpointing to manage multi-turn conversations, conditional routing, and stateful interrupts for admin approval.

The deadline for all stages is **June 9, 2026**.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │         LangGraph StateGraph                 │
                    │                                             │
User Message ──────►│  input_guardrail                            │
                    │      │                                      │
                    │      ├─ blocked ──────────────────────────► │──► output_guardrail ──► Response
                    │      │                                      │
                    │      └─ pass ──► intent_detection           │
                    │                      │                      │
                    │           ┌──────────┴──────────┐          │
                    │      info_query              reservation     │
                    │           │                      │          │
                    │        rag_node         reservation_node    │
                    │           │              (7-step collect)   │
                    │           │                      │          │
                    │           │           pending_approval      │
                    │           │                      │          │
                    │           │              admin_agent_node   │
                    │           │            ┌─────────────────┐  │
                    │           │            │ save → notify   │  │
                    │           │            │ → status check  │  │
                    │           │            └─────────────────┘  │
                    │           └──────────┬──────────┘          │
                    │                      ▼                      │
                    │              output_guardrail               │
                    │                      │                      │
                    └──────────────────────┼─────────────────────┘
                                           ▼
                                        Response

External Services:
  ┌─────────────────────────┐    ┌─────────────────────────┐
  │  Approval Server :8000   │    │  MCP Server :8001        │
  │  /approve/{id}           │───►│  write_confirmed_res()   │
  │  /reject/{id}            │    │  → data/reservations.txt │
  │  /pending                │    └─────────────────────────┘
  │  /health                 │
  │  (Chat UI + dashboard)   │
  └─────────────────────────┘

Data Layer:
  ChromaDB (static docs)  +  SQLite (dynamic: spaces, pricing, hours, reservations)
```

**State management:** `MemorySaver` checkpoints each turn; `thread_id` (UUID per session) enables multi-turn memory.

**Conditional routing:**
- After `input_guardrail`: `blocked` → `output_guardrail`, else → `intent_detection`
- After `intent_detection`: `info_query` → `rag`, `reservation` → `reservation`
- After `reservation`: `pending_approval` → `admin_agent`, else → `output_guardrail`

## Features Implemented

### Stage 1 — RAG Chatbot
- Answers questions on parking info, pricing, location, hours, availability
- ChromaDB vector store with Azure OpenAI embeddings (text-embedding-3-small-1)
- Static documents in ChromaDB; live dynamic data from SQLite injected at query time
- Semantic cache (Redis / in-memory fallback) with cosine similarity 0.92, TTL 1h
- RAG evaluation: Recall@K, Precision@K, latency measurement

### Stage 2 — Human-in-the-Loop
- 7-step interactive reservation collection with field validation
- Admin notification via email (HTML with HMAC-signed URLs) or console fallback
- FastAPI approval server with `/approve`, `/reject`, `/pending`, `/health` endpoints
- Reservation lifecycle: `pending` → `approved` / `rejected`

### Stage 3 — MCP Persistence
- FastMCP server (`write_confirmed_reservation`, `list_confirmed_reservations`)
- Concurrent-safe file writes via `filelock`
- Four-column log: `Name | Car Number | Reservation Period | Approval Time`
- Token authentication on all MCP tool calls

### Stage 4 — LangGraph Orchestration
- `StateGraph` with `MemorySaver` checkpointing
- All nodes wired with conditional edges
- Multi-turn conversation state per `thread_id`
- Load testing via `tests/test_load.py`
- Integration testing of full pipeline via `tests/test_integration.py`
- End-to-end test script (`e2e_test.py`)
- Web chat UI integrated into approval server
- CI/CD via GitHub Actions (`.github/workflows/ci.yml`)

### Guardrails (all stages)
- Input: regex-based prompt injection detection
- Output: Presidio PII anonymizer (credit cards, SSN, IBAN, passport numbers)

## Setup Instructions

### Prerequisites

- Python 3.11+
- EPAM AI Dial or Azure OpenAI API access
- spaCy model `en_core_web_lg`
- Redis (optional — in-memory fallback used if unavailable)

### Steps

```bash
# 1. Clone the repository and navigate to root
git clone <repo-url>
cd citypark-chatbot

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download spaCy model
python -m spacy download en_core_web_lg

# 5. Configure environment variables
cp .env.example .env           # or create .env from the template below
```

**`.env` configuration:**

```env
# LLM / Embeddings (EPAM AI Dial or Azure OpenAI)
DIAL_API_KEY=your_api_key
DIAL_ENDPOINT=https://your-dial-endpoint/openai
DIAL_LLM_DEPLOYMENT=gpt-4o
DIAL_EMBEDDING_DEPLOYMENT=text-embedding-3-small-1

# Admin approval server
ADMIN_SECRET_TOKEN=your-admin-token
APPROVAL_SERVER_PORT=8000

# MCP server
MCP_SECRET_TOKEN=your-mcp-token
MCP_SERVER_PORT=8001

# Optional: email notifications
ADMIN_EMAIL=admin@example.com
SENDER_EMAIL=sender@gmail.com
SENDER_APP_PASSWORD=gmail-app-password

# Optional: Redis semantic cache
REDIS_URL=redis://localhost:6379
```

## Running the Application

```bash
# First-time setup: seed database, build vector store
python main.py --setup

# Full system: chatbot + approval server (8000) + MCP server (8001)
python main.py

# Web servers only (no terminal chat)
python main.py --web-only

# Evaluate RAG performance
python main.py --evaluate

# Start all servers from helper script
python start_servers.py
```

**Access points:**
- Terminal chatbot: start with `python main.py`
- Admin dashboard: `http://localhost:8000/pending?token=<ADMIN_SECRET_TOKEN>`
- Approve: `http://localhost:8000/approve/<reservation_id>?token=<ADMIN_SECRET_TOKEN>`
- MCP health: `http://localhost:8001`

## Running Tests

```bash
# All tests
pytest -v

# Specific modules
pytest tests/test_agents.py -v
pytest tests/test_rag.py -v
pytest tests/test_guardrails.py -v
pytest tests/test_evaluation.py -v
pytest tests/test_admin.py -v
pytest tests/test_mcp_server.py -v
pytest tests/test_integration.py -v -m integration

# Load tests (requires running servers)
pytest tests/test_load.py -v -m load

# End-to-end test
python e2e_test.py
```

**Test coverage summary:**

| Test file | Tests | Scope |
|-----------|-------|-------|
| `test_agents.py` | 13 | Node functions, state transitions, routing |
| `test_guardrails.py` | 14 | Injection detection, PII anonymization |
| `test_rag.py` | 10 | Loader, vectorstore, retriever, cache |
| `test_evaluation.py` | 17 | Recall@K, Precision@K, latency |
| `test_admin.py` | 13 | Admin agent, approval server endpoints |
| `test_mcp_server.py` | 8 | MCP write, format, deduplication |
| `test_semantic_cache.py` | — | Cache hit/miss, TTL, fallback |
| `test_integration.py` | — | End-to-end pipeline flows |
| `test_load.py` | — | Concurrent request handling |

## Assignment Requirements Satisfied

| Requirement | Status |
|-------------|--------|
| Python + LangChain + LangGraph | Done |
| RAG architecture | Done — ChromaDB + Azure OpenAI embeddings |
| Vector database | Done — ChromaDB |
| Dynamic/static data split | Done — SQLite + ChromaDB |
| Information provision (hours, pricing, availability, location) | Done |
| Reservation collection (name, surname, car number, period) | Done |
| Guardrails / sensitive data protection | Done — injection filter + Presidio |
| RAG evaluation (Recall@K, Precision@K, latency) | Done |
| Human-in-the-loop admin agent | Done — FastAPI + email |
| Admin confirm/refuse via external channel | Done — email + REST API |
| MCP server for file persistence | Done — FastMCP |
| File format: Name \| Car Number \| Reservation Period \| Approval Time | Done |
| MCP server security | Done — token auth + filelock |
| LangGraph orchestration of all stages | Done — StateGraph + MemorySaver |
| Graph nodes: user interaction, admin approval, data recording | Done |
| Full pipeline integration testing | Done — test_integration.py + e2e_test.py |
| Load testing | Done — test_load.py + reports/load_test_report.json |
| Automated tests (≥2 per module) | Done — per-module test files in root tests/ |
| CI/CD | Done — .github/workflows/ci.yml |

## Project Structure

```
citypark-chatbot/
├── main.py                        # Entry point (chat / --setup / --evaluate / --web-only)
├── start_servers.py               # Helper to start all servers
├── e2e_test.py                    # End-to-end test script
├── requirements.txt
├── pytest.ini                     # Markers: integration, load
├── conftest.py
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions CI pipeline
├── data/
│   ├── static/                    # 8 static documents → ChromaDB
│   ├── dynamic/
│   │   └── parking.db             # SQLite: spaces, pricing, hours, reservations
│   ├── chroma_db/                 # Persistent ChromaDB vector store
│   └── reservations.txt           # MCP-written confirmed reservations log
├── src/
│   ├── config.py                  # All environment variables and constants
│   ├── agents/
│   │   ├── state.py               # ReservationState TypedDict
│   │   ├── nodes.py               # All pipeline node functions
│   │   └── graph.py               # LangGraph StateGraph definition + compile
│   ├── rag/
│   │   ├── loader.py              # Document loading and chunking
│   │   ├── vectorstore.py         # ChromaDB + AzureOpenAI embeddings
│   │   ├── retriever.py           # Similarity-search retriever
│   │   └── semantic_cache.py      # Redis / in-memory semantic cache
│   ├── admin/
│   │   ├── agent.py               # Admin orchestration agent (@tool: save, notify, check)
│   │   ├── approval_server.py     # FastAPI: approval dashboard + API + chat UI
│   │   └── email_service.py       # Email service with console fallback
│   ├── mcp_server/
│   │   ├── server.py              # FastMCP server (write + list tools)
│   │   └── client.py             # Sync MCP client wrapper
│   ├── database/
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   ├── seed.py                # Database seeding
│   │   └── queries.py             # All database query functions
│   ├── guardrails/
│   │   └── filters.py             # InputFilter + OutputFilter
│   └── evaluation/
│       ├── metrics.py             # RAG evaluation metrics
│       └── test_dataset.json      # 20 annotated Q&A pairs
├── tests/
│   ├── test_agents.py
│   ├── test_rag.py
│   ├── test_guardrails.py
│   ├── test_evaluation.py
│   ├── test_admin.py
│   ├── test_mcp_server.py
│   ├── test_semantic_cache.py
│   ├── test_integration.py
│   └── test_load.py
├── docs/
│   └── graph_architecture.md
├── reports/
│   └── load_test_report.json
├── scripts/
│   ├── fix_dashboard.py
│   └── generate_graph_diagram.py
└── releases/
    ├── stage1/                    # Stage 1 snapshot (RAG chatbot)
    ├── stage2/                    # Stage 2 snapshot (+ admin approval)
    └── stage3/                    # Stage 3 snapshot (+ MCP server)
```

## Future Improvements

- Replace manual `run_admin_agent` orchestration with `create_react_agent` for true LangChain agent behavior
- Add real-time user notification (websocket or polling) when reservation is approved
- Migrate from ChromaDB to a production vector database (Pinecone or Weaviate)
- Add Terraform IaC for cloud deployment
- Extend evaluation with RAGAS framework for more granular RAG quality metrics
- Add structured JSON export from MCP server alongside plain-text log
- Containerize with Docker Compose (chatbot + approval server + MCP server + Redis)
