import os
import sys
import uuid
import time
from langchain_core.messages import HumanMessage

from src.database.seed import seed_database
from src.rag.vectorstore import load_vectorstore
from src.agents.graph import app
from src.admin.approval_server import start_server_thread, set_graph
from src.mcp_server.server import start_mcp_server_thread


def setup():
    print("Initializing CityPark chatbot...")
    print("  [1/2] Seeding database...")
    seed_database()
    print("  [2/2] Building vector store (this may take a moment on first run)...")
    load_vectorstore()
    print("Setup complete.\n")


def ensure_setup():
    from src.config import SQLITE_DB_PATH, CHROMA_PERSIST_DIR
    db_ready = os.path.exists(SQLITE_DB_PATH)
    chroma_ready = os.path.exists(CHROMA_PERSIST_DIR) and bool(os.listdir(CHROMA_PERSIST_DIR))
    if not db_ready or not chroma_ready:
        setup()


def _make_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def chat():
    ensure_setup()

    # Wire approval server so it can resume the graph
    set_graph(app, _make_config)
    start_mcp_server_thread()
    start_server_thread()
    time.sleep(1.0)  # let both servers bind their ports

    thread_id = str(uuid.uuid4())
    config = _make_config(thread_id)

    print("=" * 56)
    print("  Welcome to CityPark Premium Parking Assistant!")
    print("=" * 56)
    print(f"  Web chat UI : http://localhost:{os.environ.get('APPROVAL_SERVER_PORT', 8000)}")
    print(f"  Admin portal: http://localhost:{os.environ.get('APPROVAL_SERVER_PORT', 8000)}/pending")
    print("  Terminal mode: type below (or use the web UI above)")
    print("  Commands: 'new' = new session | 'exit' = quit")
    print("-" * 56)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye! Thank you for using CityPark.")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("Goodbye! Thank you for using CityPark.")
            break

        if user_input.lower() == "new":
            thread_id = str(uuid.uuid4())
            config = _make_config(thread_id)
            print("New session started.\n")
            continue

        try:
            result = app.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )
            response = result.get("response", "I'm sorry, something went wrong. Please try again.")
        except Exception as e:
            if "interrupt" in str(e).lower() or "NodeInterrupt" in type(e).__name__:
                response = (
                    "Your reservation has been submitted and is awaiting administrator approval.\n"
                    "You will be notified once it is reviewed. Is there anything else I can help with?"
                )
            else:
                response = f"An error occurred: {e}"

        print(f"\nAssistant: {response}\n")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
    elif "--evaluate" in sys.argv:
        from src.evaluation.metrics import run_evaluation
        ensure_setup()
        print("Running RAG evaluation...")
        results = run_evaluation(k=4)
        print("\nEvaluation Results:")
        for key, value in results.items():
            print(f"  {key:<30}: {value}")
    elif "--web-only" in sys.argv:
        import threading
        ensure_setup()
        set_graph(app, _make_config)
        start_mcp_server_thread()
        start_server_thread()
        port = os.environ.get("APPROVAL_SERVER_PORT", 8000)
        print("=" * 56)
        print("  CityPark Premium Parking — Web Server Mode")
        print("=" * 56)
        print(f"  Web chat UI : http://localhost:{port}")
        print(f"  Admin portal: http://localhost:{port}/pending")
        print("  Press Ctrl+C to stop.")
        print("-" * 56)
        stop = threading.Event()
        try:
            stop.wait()
        except KeyboardInterrupt:
            print("\nShutting down. Goodbye!")
    else:
        chat()
