from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class ReservationState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    retrieved_context: str
    reservation_data: dict
    collection_step: str
    guardrail_blocked: bool
    response: str
    reservation_id: str
    approval_status: str
    user_profile: dict
