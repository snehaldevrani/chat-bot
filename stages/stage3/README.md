# CityPark Chatbot — Stage 3: MCP Server for Reservation Persistence

## Overview

Stage 3 adds a Model Context Protocol (MCP) server that acts as the final step in the reservation pipeline. When an administrator approves a reservation, the approval server calls the MCP server, which writes the confirmed reservation to a persistent text log in the required four-column format. The MCP server is implemented using FastMCP (Python) and runs on a separate port, isolated from the approval server.

## Architecture

```
User Input
    │
    ▼
┌──────────────────┐    ┌──────────────────────────────────────┐
│  Chatbot Pipeline │    │  MCP Server (port 8001)               │
│  (Stage 1 RAG +  │    │  Tools:                               │
│   Stage 2 Admin) │    │  ├── write_confirmed_reservation()    │
│                  │    │  │     → reservations.txt (4-column)  │
│  After approval: │───►│  └── list_confirmed_reservations()   │
│  approval_server │    └──────────────────────────────────────┘
│  calls MCP client│
└──────────────────┘

Approval Server (port 8000)
  GET /approve/{id}?token=...
     │
     ├── 1. Update DB: status = "approved", reviewed_at = now
     └── 2. Call _write_to_mcp(record)
              │
              └── MCP Client → HTTP → MCP Server
                       └── Writes to data/reservations.txt

reservations.txt format:
  # CityPark Premium Parking - Confirmed Reservations Log
  # Format: Name | Car Number | Reservation Period | Approval Time
  John Smith | AB12XYZ | 2026-06-15 09:00 to 2026-06-15 18:00 | 2026-06-08 14:30:45
```

**New components added in Stage 3:**
- **MCP Server** (`src/mcp_server/server.py`): FastMCP server exposing `write_confirmed_reservation` and `list_confirmed_reservations` tools.
- **MCP Client** (`src/mcp_server/client.py`): Synchronous wrapper calling the MCP server via streamable-HTTP transport.
- **File locking**: `filelock` ensures concurrent-safe writes to `reservations.txt`.
- **Token auth**: MCP server validates `MCP_SECRET_TOKEN` on every tool call.

## Features Implemented

All Stage 1 and Stage 2 features, plus:

- FastMCP server running in a background thread on port 8001
- `write_confirmed_reservation` tool — appends approved reservations to `data/reservations.txt`
- `list_confirmed_reservations` tool — reads and returns all confirmed records
- Four-column format: `Full Name | Car Number | Start to End | Approval Time`
- Duplicate prevention (skips if reservation ID already in log)
- Concurrent-safe writes via `filelock`
- HMAC token authentication on MCP endpoints
- Automatic `approval_time` generation if not provided by caller

## Setup Instructions

### Prerequisites

- Python 3.11+
- Access to EPAM AI Dial or Azure OpenAI
- spaCy model `en_core_web_lg`

### Steps

```bash
cd releases/stage3

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m spacy download en_core_web_lg

cp ../../.env .env
```

**Required `.env` variables (additions for Stage 3):**

```env
# Stage 1 + 2 variables (same as before)
DIAL_API_KEY=your_api_key
DIAL_ENDPOINT=https://your-dial-endpoint/openai
DIAL_LLM_DEPLOYMENT=gpt-4o
DIAL_EMBEDDING_DEPLOYMENT=text-embedding-3-small-1
ADMIN_SECRET_TOKEN=your-secret-admin-token

# Stage 3 additions
MCP_SECRET_TOKEN=your-mcp-secret-token
MCP_SERVER_PORT=8001
```

## Running the Application

```bash
# First-time setup
python main.py --setup

# Start chatbot + approval server (8000) + MCP server (8001)
python main.py

# Start only the web servers (no terminal chat)
python main.py --web-only
```

**Servers started:**
- Chatbot — terminal interface
- Admin Approval Server — `http://localhost:8000`
- MCP Server — `http://localhost:8001`

**Trigger the full flow:**
1. Chat with the bot and complete a reservation request.
2. Admin approves via `http://localhost:8000/approve/<id>?token=<ADMIN_SECRET_TOKEN>`.
3. MCP server writes the record to `data/reservations.txt`.

**Verify the log:**
```bash
cat data/reservations.txt
```
Expected output:
```
# CityPark Premium Parking - Confirmed Reservations Log
# Format: Name | Car Number | Reservation Period | Approval Time
Snehal Devrani | MH04AB1234 | 2026-06-15 09:00 to 2026-06-15 18:00 | 2026-06-08 14:30:45
```

## Running Tests

```bash
cd releases/stage3
pytest -v
```

**Test file:** `tests/test_stage3_snapshot.py`

| Test | Description |
|------|-------------|
| `test_mcp_writer_uses_required_four_column_format` | Verifies exact 4-column output format |
| `test_approval_server_calls_mcp_on_approve` | Confirms approval triggers `_write_to_mcp` |
| `test_stage3_has_mcp_but_no_graph_module` | Confirms MCP present, LangGraph absent (Stage 4 only) |

## Assignment Requirements Satisfied

| Requirement | Status |
|-------------|--------|
| MCP server to write data to file | Done — FastMCP server with `write_confirmed_reservation` tool |
| Write triggered after admin approval | Done — approval server calls MCP client on approve |
| File format: Name \| Car Number \| Reservation Period \| Approval Time | Done — exact format verified by test |
| Server security (unauthorized access prevention) | Done — HMAC token required on all tool calls |
| Reliable service (concurrent writes) | Done — `filelock` prevents data corruption |
| Integration with previous agents | Done — MCP client called from approval server endpoint |
| Automated tests (pytest) | Done — 48 tests across 7 test files (per-module coverage) |

## Project Structure

```
releases/stage3/
├── main.py                        # Entry point; starts approval + MCP server threads
├── requirements.txt               # Adds mcp>=1.0.0, filelock>=3.0.0
├── pytest.ini
├── conftest.py
├── data/
│   └── static/                    # 8 static documents (same as Stage 1)
├── src/
│   ├── config.py                  # Adds: MCP_SERVER_PORT, MCP_SERVER_URL, MCP_SECRET_TOKEN, RESERVATIONS_FILE
│   ├── mcp_server/
│   │   ├── server.py              # FastMCP server: write_confirmed_reservation, list_confirmed_reservations
│   │   └── client.py             # Sync MCP client wrapper (call_mcp_write)
│   ├── admin/
│   │   ├── agent.py               # Unchanged from Stage 2 (create_react_agent + @tool)
│   │   ├── approval_server.py     # /approve now calls _write_to_mcp via MCP client
│   │   └── email_service.py       # Unchanged from Stage 2
│   ├── agents/                    # Unchanged from Stage 2
│   ├── rag/                       # Unchanged from Stage 1
│   ├── database/                  # Unchanged from Stage 2
│   ├── guardrails/                # Unchanged from Stage 1
│   └── evaluation/                # Unchanged from Stage 1
└── tests/
    ├── test_stage3_snapshot.py
    ├── test_database.py
    ├── test_email_service.py
    ├── test_evaluation.py
    ├── test_guardrails.py
    ├── test_mcp_client.py
    └── test_rag.py
```

## Future Improvements

- Add LangGraph orchestration to manage the MCP write as a graph node (implemented in Stage 4)
- Expose `list_confirmed_reservations` through the admin dashboard UI
- Add structured JSON or CSV export alongside the plain-text log
- Implement MCP server health check endpoint
