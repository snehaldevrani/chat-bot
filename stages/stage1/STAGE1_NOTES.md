# Stage 1 Notes

This snapshot contains only the Stage 1 RAG chatbot scope:

- static document loading and chunking
- Chroma vector store integration
- information retrieval and response generation
- dynamic SQLite parking data for availability, pricing, and hours
- interactive reservation detail collection
- input/output guardrails
- retrieval evaluation metrics

Removed from this snapshot:

- administrator approval workflow
- admin email/server modules
- MCP reservation persistence
- Stage 4 LangGraph graph orchestration
- user auth, dashboards, notifications, generated databases, vector stores, logs, and caches

Run:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg
python main.py --setup
python main.py
pytest
```
