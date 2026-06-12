from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.agents.state import ReservationState
from src.agents.nodes import (
    input_guardrail_node,
    intent_detection_node,
    rag_node,
    reservation_node,
    admin_agent_node,
    output_guardrail_node,
)


def _route_after_guardrail(state: ReservationState) -> str:
    return "blocked" if state.get("guardrail_blocked") else "pass"


def _route_after_intent(state: ReservationState) -> str:
    return "reservation" if state.get("intent") == "reservation" else "info_query"


def _route_after_reservation(state: ReservationState) -> str:
    return "admin" if state.get("collection_step") == "pending_approval" else "output"


def build_graph():
    graph = StateGraph(ReservationState)

    graph.add_node("input_guardrail", input_guardrail_node)
    graph.add_node("intent_detection", intent_detection_node)
    graph.add_node("rag", rag_node)
    graph.add_node("reservation", reservation_node)
    graph.add_node("admin_agent", admin_agent_node)
    graph.add_node("output_guardrail", output_guardrail_node)

    graph.set_entry_point("input_guardrail")

    graph.add_conditional_edges(
        "input_guardrail",
        _route_after_guardrail,
        {"blocked": "output_guardrail", "pass": "intent_detection"},
    )
    graph.add_conditional_edges(
        "intent_detection",
        _route_after_intent,
        {"info_query": "rag", "reservation": "reservation"},
    )
    graph.add_conditional_edges(
        "reservation",
        _route_after_reservation,
        {"admin": "admin_agent", "output": "output_guardrail"},
    )
    graph.add_edge("rag", "output_guardrail")
    graph.add_edge("admin_agent", "output_guardrail")
    graph.add_edge("output_guardrail", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


app = build_graph()
