# Reconstruction Report

Created three runnable project snapshots under `releases/` while preserving the root project as the Stage 4 version.

## Snapshot directories

- `releases/stage1`
- `releases/stage2`
- `releases/stage3`

The snapshots were built from selected root project files and then trimmed so each stage contains only the requested scope. Generated artifacts and local-only files were excluded or removed:

- `.env`
- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- `data/chroma_db/`
- `data/dynamic/parking.db`
- `data/reservations.txt`
- reservation lock files
- root-only scripts/docs that belong to Stage 4 or later polish

## Stage 1 snapshot

Path: `releases/stage1`

Included functionality:

- RAG document loading, chunking, embeddings, Chroma vector store support
- information retrieval
- dynamic SQLite support for parking availability, pricing, and working hours
- reservation detail collection
- guardrails
- retrieval evaluation
- semantic cache support

Removed functionality:

- administrator approval workflow
- email/admin server modules
- MCP server and MCP client
- Stage 4 LangGraph graph orchestration
- user authentication, dashboards, notifications, and chat persistence

Important files added or adjusted:

- `main.py`: standalone Stage 1 runner with setup, chat, and evaluation modes
- `src/config.py`: Stage 1-only configuration
- `src/agents/nodes.py`: non-LangGraph Stage 1 RAG/reservation/guardrail flow
- `src/database/models.py`, `queries.py`, `seed.py`: trimmed to parking data and simple reservation records
- `requirements.txt`: Stage 1 dependency set
- `STAGE1_NOTES.md`
- `tests/test_stage1_snapshot.py`

Verification:

```text
cd releases/stage1
pytest -q
4 passed, 1 warning
python -c "import main; print('stage1 import ok')"
stage1 import ok
```

## Stage 2 snapshot

Path: `releases/stage2`

Included functionality:

- all Stage 1 functionality
- administrator notification service
- human-in-the-loop approval server
- pending reservation listing
- approve/reject endpoints backed by SQLite reservation status

Removed functionality:

- MCP server and MCP client
- approved-reservation file persistence
- Stage 4 LangGraph graph orchestration
- user authentication, dashboards, notifications, and chat persistence

Important files added or adjusted:

- `main.py`: standalone Stage 2 runner with admin server startup
- `src/config.py`: Stage 1 + Stage 2 configuration only
- `src/admin/agent.py`: deterministic admin-agent wrapper using LangChain tools, without Stage 4 graph orchestration
- `src/admin/approval_server.py`: minimal FastAPI approval server
- `src/agents/nodes.py`: reservation confirmation submits to admin agent
- `requirements.txt`: Stage 2 dependency set, no MCP package
- `STAGE2_NOTES.md`
- `tests/test_stage2_snapshot.py`

Verification:

```text
cd releases/stage2
pytest -q
3 passed, 15 warnings
python -c "import main; print('stage2 import ok')"
stage2 import ok
```

## Stage 3 snapshot

Path: `releases/stage3`

Included functionality:

- all Stage 1 functionality
- all Stage 2 administrator approval functionality
- MCP server and MCP client for approved reservation persistence
- secure token check for MCP writes
- file locking for concurrent-safe reservation log writes

Removed functionality:

- Stage 4 LangGraph graph orchestration
- user authentication, dashboards, notifications, and chat persistence

Important files added or adjusted:

- `main.py`: standalone Stage 3 runner with admin and MCP server startup
- `src/config.py`: Stage 1 + Stage 2 + Stage 3 configuration
- `src/admin/approval_server.py`: minimal FastAPI approval server that writes to MCP after approval
- `src/mcp_server/server.py`: cleaned Stage 3 MCP server using the assignment-required four-column format:
  `Name | Car Number | Reservation Period | Approval Time`
- `requirements.txt`: Stage 3 dependency set
- `STAGE3_NOTES.md`
- `tests/test_stage3_snapshot.py`

Verification:

```text
cd releases/stage3
pytest -q
3 passed, 15 warnings
python -c "import main; print('stage3 import ok')"
stage3 import ok
```

## Root project preservation

The root project remains the Stage 4 version. No root application functionality was edited. Root-level changes made for this task were limited to:

- adding `releases/stage1`
- adding `releases/stage2`
- adding `releases/stage3`
- adding this `RECONSTRUCTION_REPORT.md`

`STAGE_BREAKDOWN.md` was already present from the prior task and was used as the reconstruction guide.

## Notes

- Full `python main.py --setup` in each snapshot still requires live embedding credentials because it builds the Chroma vector store. The import/startup checks avoid external API calls while verifying that each snapshot imports independently.
- Tests intentionally mock or avoid external LLM/vector calls where appropriate.
- Stage 2 and Stage 3 use development default tokens for local startability. Real submissions should set `ADMIN_SECRET_TOKEN`, and Stage 3 should also set `MCP_SECRET_TOKEN`.
