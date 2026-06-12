import os
import sys
import threading
import uuid
from langchain_core.messages import HumanMessage

from src.admin.approval_server import start_server_thread
from src.agents.nodes import (
    input_guardrail_node,
    intent_detection_node,
    output_guardrail_node,
    rag_node,
    reservation_node,
)
from src.database.seed import seed_database
from src.rag.vectorstore import load_vectorstore


def setup():
    print("Initializing Stage 2 CityPark chatbot...")
    seed_database()
    load_vectorstore()
    print("Setup complete.")


def ensure_setup():
    from src.config import SQLITE_DB_PATH, CHROMA_PERSIST_DIR

    db_ready = os.path.exists(SQLITE_DB_PATH)
    chroma_ready = os.path.exists(CHROMA_PERSIST_DIR) and bool(os.listdir(CHROMA_PERSIST_DIR))
    if not db_ready or not chroma_ready:
        setup()


def handle_message(message: str, state: dict | None = None) -> dict:
    state = dict(state or {})
    state.setdefault("thread_id", str(uuid.uuid4()))
    state["messages"] = [HumanMessage(content=message)]
    state.update(input_guardrail_node(state))
    if state.get("guardrail_blocked"):
        state.update(output_guardrail_node(state))
        return state
    state.update(intent_detection_node(state))
    if state["intent"] == "reservation":
        state.update(reservation_node(state))
    else:
        state.update(rag_node(state))
    state.update(output_guardrail_node(state))
    return state


def chat():
    ensure_setup()
    start_server_thread()
    state = {"thread_id": str(uuid.uuid4())}
    print("CityPark Stage 2 chatbot. Admin approval server is running. Type 'exit' to quit.")
    while True:
        text = input("You: ").strip()
        if text.lower() == "exit":
            break
        state.update(handle_message(text, state))
        print(f"Assistant: {state.get('response', '')}\n")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
    elif "--evaluate" in sys.argv:
        ensure_setup()
        from src.evaluation.metrics import run_evaluation

        print(run_evaluation(k=4))
    elif "--web-only" in sys.argv:
        ensure_setup()
        start_server_thread()
        threading.Event().wait()
    else:
        chat()
