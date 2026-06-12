# CityPark Chatbot — Stage 2: Human-in-the-Loop Admin Approval

## Overview

Stage 2 extends the Stage 1 chatbot with a Human-in-the-Loop workflow. Once a user completes a reservation request, the system automatically escalates it to an administrator for approval. The admin receives a notification (email or console fallback) with approve/reject links, and a FastAPI web server processes the admin's decision. The user's reservation moves from `pending` to `approved` or `rejected` based on the admin's response.

## Architecture

```
User Input
    │
    ▼
┌─────────────────────────┐
│   Input Guardrail        │
└────────────┬────────────┘
             │
    ┌────────▼────────┐
    │ Intent Detection │
    └───┬─────────┬───┘
        │         │
   ┌────▼───┐  ┌──▼──────────────────────────────────────────┐
   │  RAG   │  │  Reservation Node                            │
   │  Node  │  │  (7-step collection → status: "pending")     │
   └────┬───┘  └──────────────────┬───────────────────────────┘
        │                         │ on confirmation
        │              ┌──────────▼──────────────┐
        │              │   Admin Agent            │
        │              │   ├── save_reservation   │  → SQLite (status: pending)
        │              │   ├── notify_admin       │  → Email / console URLs
        │              │   └── check_status       │
        │              └─────────────────────────┘
        │
        ▼
   ┌───────────────────────┐
   │   Output Guardrail    │
   └───────────────────────┘

   ┌───────────────────────────────────────────────┐
   │  FastAPI Approval Server (port 8000)           │
   │  GET /approve/{id}?token=...  → status=approved │
   │  GET /reject/{id}?token=...   → status=rejected │
   │  GET /pending?token=...       → list pending    │
   │  GET /health                  → liveness check  │
   └───────────────────────────────────────────────┘
```

**New components added in Stage 2:**
- **Admin Agent** (`src/admin/agent.py`): a formal LangChain agent built with `create_react_agent` (`langgraph.prebuilt`) and `AzureChatOpenAI`, using three `@tool`-decorated functions to save the reservation, notify the admin, and check status.
- **Email Service** (`src/admin/email_service.py`): sends HTML email with signed approve/reject URLs; falls back to console output for local development.
- **Approval Server** (`src/admin/approval_server.py`): FastAPI server handling admin decisions via HMAC-token-authenticated endpoints.

## Features Implemented

All Stage 1 features, plus:

- Admin notification via email (HTML with approve/reject buttons) or console fallback
- HMAC-signed approve/reject URLs for tamper-resistant decisions
- FastAPI approval server running in a background thread
- Reservation lifecycle: `pending` → `approved` / `rejected`
- Admin dashboard at `GET /pending` showing all pending reservations
- Two-agent architecture: chatbot agent (Stage 1) + admin orchestration agent (Stage 2)
- `reviewed_at` timestamp and `admin_notes` captured on decision

## Setup Instructions

### Prerequisites

- Python 3.11+
- Access to EPAM AI Dial or Azure OpenAI
- spaCy model `en_core_web_lg`
- Optional: Gmail account with App Password for email notifications

### Steps

```bash
cd releases/stage2

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m spacy download en_core_web_lg

cp ../../.env .env
```

**Required `.env` variables (additions for Stage 2):**

```env
# Stage 1 variables (same as before)
DIAL_API_KEY=your_api_key
DIAL_ENDPOINT=https://your-dial-endpoint/openai
DIAL_LLM_DEPLOYMENT=gpt-4o
DIAL_EMBEDDING_DEPLOYMENT=text-embedding-3-small-1

# Stage 2 additions
ADMIN_SECRET_TOKEN=your-secret-admin-token
APPROVAL_SERVER_PORT=8000

# Optional: email notifications
ADMIN_EMAIL=admin@example.com
SENDER_EMAIL=your-gmail@gmail.com
SENDER_APP_PASSWORD=your-app-password
```

If email variables are not set, approve/reject URLs are printed to the console instead.

## Running the Application

```bash
# First-time setup
python main.py --setup

# Start chatbot + approval server (port 8000)
python main.py

# Start only the approval server (no terminal chat)
python main.py --web-only
```

**Admin workflow:**
1. User completes reservation → system prints (or emails) approval/rejection URLs.
2. Admin visits: `http://localhost:8000/approve/<reservation_id>?token=<ADMIN_SECRET_TOKEN>`
3. Reservation status changes to `approved` in the database.

**Check pending reservations:**
```
http://localhost:8000/pending?token=<ADMIN_SECRET_TOKEN>
```

## Running Tests

```bash
cd releases/stage2
pytest -v
```

**Test file:** `tests/test_stage2_snapshot.py`

| Test | Description |
|------|-------------|
| `test_admin_agent_creates_pending_reservation` | Admin agent saves reservation with `pending` status |
| `test_approval_server_approves_without_mcp` | Approval endpoint updates status to `approved` |
| `test_stage2_has_no_mcp_or_graph_modules` | Confirms no Stage 3/4 code is present |

## Assignment Requirements Satisfied

| Requirement | Status |
|-------------|--------|
| Second agent using LangChain | Done — `run_admin_agent` uses `create_react_agent` (`langgraph.prebuilt`) with `AzureChatOpenAI` and three `@tool`-decorated functions |
| Send reservation request to admin | Done — email with signed URLs, console fallback |
| Admin can confirm or refuse | Done — `/approve` and `/reject` FastAPI endpoints |
| Integration with first agent | Done — reservation node calls `run_admin_agent` on confirmation |
| Generating and sending confirmation requests | Done — email service with HTML template |
| Receiving responses from administrator | Done — FastAPI server captures decision + timestamp |
| Communication between agents | Done — shared SQLite database for state, admin agent updates status |
| Automated tests (pytest) | Done — 45 tests across 6 test files (per-module coverage) |

## Project Structure

```
releases/stage2/
├── main.py                        # Entry point; starts approval server thread
├── requirements.txt               # Adds fastapi, uvicorn, python-multipart
├── pytest.ini
├── conftest.py
├── data/static/                   # 8 static documents (same as Stage 1)
├── src/
│   ├── config.py                  # Adds: ADMIN_EMAIL, SENDER_EMAIL, APPROVAL_SERVER_URL/PORT, ADMIN_SECRET_TOKEN
│   ├── admin/
│   │   ├── agent.py               # run_admin_agent via create_react_agent + @tool: save, notify, check_status
│   │   ├── approval_server.py     # FastAPI: /health, /pending, /approve/{id}, /reject/{id}
│   │   └── email_service.py       # HTML email with signed URLs; console fallback
│   ├── agents/
│   │   ├── state.py               # Adds: approval_status field
│   │   └── nodes.py               # reservation_node now calls run_admin_agent on confirm
│   ├── rag/                       # Unchanged from Stage 1
│   ├── database/
│   │   ├── models.py              # Reservation.status can be: pending/approved/rejected
│   │   └── queries.py             # Adds: get_pending_reservations, approve_reservation, reject_reservation
│   ├── guardrails/                # Unchanged from Stage 1
│   └── evaluation/                # Unchanged from Stage 1
└── tests/
    ├── test_stage2_snapshot.py
    ├── test_database.py
    ├── test_email_service.py
    ├── test_evaluation.py
    ├── test_guardrails.py
    └── test_rag.py
```

## Future Improvements

- Add webhook / polling support so the chatbot can inform the user when their request is approved
- Add LangGraph orchestration for stateful interrupt/resume (implemented in Stage 4)
- Rate-limit the approval endpoints to prevent replay attacks
