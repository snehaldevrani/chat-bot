from typing_extensions import TypedDict


class ReservationState(TypedDict, total=False):
    intent: str
    retrieved_context: str
    reservation_data: dict
    collection_step: str
    guardrail_blocked: bool
    response: str
    reservation_id: str
    approval_status: str
