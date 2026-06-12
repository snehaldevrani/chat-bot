# Stage 2 Notes

This snapshot contains Stage 1 plus the Stage 2 human-in-the-loop administrator workflow:

- all Stage 1 RAG, guardrail, reservation collection, and evaluation files
- admin notification service with email and console fallback
- admin approval FastAPI server
- approve/reject endpoints backed by SQLite reservation status

Removed from this snapshot:

- MCP server and MCP client
- approved-reservation file persistence
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

Default local admin token: `stage2-dev-admin-token`.
Set `ADMIN_SECRET_TOKEN` in `.env` for a real deployment.
