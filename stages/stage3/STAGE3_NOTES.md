# Stage 3 Notes

This snapshot contains Stage 1 plus Stage 2 plus Stage 3 MCP persistence:

- all Stage 1 RAG, guardrail, reservation collection, and evaluation files
- Stage 2 administrator approval workflow
- MCP server and client for writing approved reservations
- assignment-required reservation log format:
  `Name | Car Number | Reservation Period | Approval Time`

Removed from this snapshot:

- Stage 4 LangGraph graph orchestration
- user auth, dashboards, notifications, generated databases, vector stores, logs, and caches

Run:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg
python main.py --setup
python main.py --web-only
pytest
```

Default local admin token: `stage3-dev-admin-token`.
Default local MCP token: `stage3-dev-mcp-token`.
Set `ADMIN_SECRET_TOKEN` and `MCP_SECRET_TOKEN` in `.env` for a real deployment.
