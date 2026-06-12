import json
import re
from datetime import datetime, timezone, timedelta
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from src.config import DIAL_API_KEY, DIAL_ENDPOINT, DIAL_API_VERSION, DIAL_LLM_DEPLOYMENT, RETRIEVER_K
from src.database.queries import get_availability_summary, get_pricing_summary, get_hours_summary
from src.guardrails.filters import get_input_filter, get_output_filter
from src.rag.semantic_cache import get_semantic_cache
from src.rag.vectorstore import get_embeddings, get_vectorstore

COLLECTION_ORDER = ["name", "surname", "car_number", "start_datetime", "end_datetime", "space_type"]
SPACE_RATES = {"regular": 3.0, "ev_charging": 5.0, "vip": 8.0, "handicapped": 2.0}
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.IGNORECASE)
_NAME_RE = re.compile(r"^[A-Za-z' -]{1,60}$")
_CAR_RE = re.compile(r"^[A-Z0-9][A-Z0-9 -]{1,14}$", re.IGNORECASE)
_llm = None


def get_llm() -> AzureChatOpenAI:
    global _llm
    if _llm is None:
        _llm = AzureChatOpenAI(
            azure_deployment=DIAL_LLM_DEPLOYMENT,
            azure_endpoint=DIAL_ENDPOINT,
            api_key=DIAL_API_KEY,
            api_version=DIAL_API_VERSION,
            temperature=0.1,
        )
    return _llm


def _last_text(state: dict) -> str:
    messages = state.get("messages", [])
    if not messages:
        return state.get("message", "")
    msg = messages[-1]
    return getattr(msg, "content", str(msg)).strip()


def _parse_time(value: str) -> str | None:
    m = _TIME_RE.match(value.strip())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem == "am":
        hour = 0 if hour == 12 else hour
    elif meridiem == "pm":
        hour = hour if hour == 12 else hour + 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _parse_datetime(value: str) -> str | None:
    v = value.strip()
    if _DATETIME_RE.match(v):
        return v
    today = datetime.now(timezone.utc).date()
    lower = v.lower()
    if lower.startswith("tomorrow"):
        date = today + timedelta(days=1)
        time_part = lower[8:].strip().removeprefix("at").strip()
    elif lower.startswith("today"):
        date = today
        time_part = lower[5:].strip().removeprefix("at").strip()
    else:
        date = today
        time_part = lower
    parsed_time = _parse_time(time_part)
    if not parsed_time:
        return None
    return f"{date:%Y-%m-%d} {parsed_time}"


def _validate_field(step: str, value: str) -> str | None:
    v = value.strip()
    if not v:
        return "This field cannot be empty."
    if step in ("name", "surname") and not _NAME_RE.match(v):
        return "Please enter a valid name."
    if step == "car_number" and not _CAR_RE.match(v):
        return "Please enter a valid car number."
    if step in ("start_datetime", "end_datetime") and _parse_datetime(v) is None:
        return "Please enter a time like 9am, tomorrow 14:00, or 2026-06-15 09:00."
    if step == "space_type" and v.lower() not in SPACE_RATES:
        return "Please choose regular, ev_charging, vip, or handicapped."
    return None


def _normalize_value(step: str, value: str) -> str:
    if step in ("start_datetime", "end_datetime"):
        return _parse_datetime(value) or value.strip()
    return value.strip()


def input_guardrail_node(state: dict) -> dict:
    blocked, reason = get_input_filter().check(_last_text(state))
    if blocked:
        return {
            "guardrail_blocked": True,
            "response": f"I cannot process that request. {reason} Please ask about parking information or reservations.",
        }
    return {"guardrail_blocked": False}


def intent_detection_node(state: dict) -> dict:
    if state.get("collection_step"):
        return {"intent": "reservation"}
    text = _last_text(state).lower()
    if any(word in text for word in ["book", "reserve", "reservation", "parking space"]):
        return {"intent": "reservation"}
    return {"intent": "info_query"}


def rag_node(state: dict) -> dict:
    query = _last_text(state)
    embedding_model = get_embeddings()
    query_embedding = embedding_model.embed_query(query)
    cache = get_semantic_cache()
    cached = cache.lookup(query_embedding)
    if cached is not None:
        return {"retrieved_context": "", "response": cached}

    docs = get_vectorstore().similarity_search_by_vector(query_embedding, k=RETRIEVER_K)
    rag_context = "\n\n---\n\n".join(doc.page_content for doc in docs)
    dynamic_context = "\n".join([get_availability_summary(), "", get_pricing_summary(), "", get_hours_summary()])
    response = get_llm().invoke([
        SystemMessage(content=(
            "You are a helpful CityPark Premium Parking assistant. "
            "Answer only from the supplied context.\n\n"
            f"KNOWLEDGE BASE:\n{rag_context}\n\nLIVE DATA:\n{dynamic_context}"
        )),
        HumanMessage(content=query),
    ])
    cache.store(query_embedding, response.content, query)
    return {"retrieved_context": rag_context, "response": response.content}


def _extract_fields_from_message(message: str) -> dict:
    try:
        response = get_llm().invoke([
            SystemMessage(content=(
                "Extract parking reservation details. Return only JSON with keys "
                "name, surname, car_number, start_datetime, end_datetime, space_type. "
                "Use null for missing fields."
            )),
            HumanMessage(content=message),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        return {k: v.strip() for k, v in data.items() if isinstance(v, str) and v.strip()}
    except Exception:
        return {}


def _next_prompt(step: str, data: dict) -> str:
    prompts = {
        "name": "What is your first name?",
        "surname": f"Nice to meet you, {data.get('name', '')}! What is your surname?",
        "car_number": "What is your car registration number?",
        "start_datetime": "What time would you like the reservation to start?",
        "end_datetime": "What time should the reservation end?",
        "space_type": "What type of space do you prefer: regular, ev_charging, vip, or handicapped?",
    }
    return prompts[step]


def _build_summary(data: dict) -> str:
    return (
        "Reservation Summary:\n"
        f"Name: {data.get('name', '')} {data.get('surname', '')}\n"
        f"Car Number: {data.get('car_number', '')}\n"
        f"Start: {data.get('start_datetime', '')}\n"
        f"End: {data.get('end_datetime', '')}\n"
        f"Space Type: {data.get('space_type', 'regular')}\n\n"
        "Type 'confirm' to save this request locally or 'cancel' to start over."
    )


def reservation_node(state: dict) -> dict:
    text = _last_text(state)
    step = state.get("collection_step", "")
    data = dict(state.get("reservation_data") or {})
    if text.lower() in ("cancel", "stop", "quit", "exit", "no"):
        return {"collection_step": "", "reservation_data": {}, "response": "Reservation cancelled."}
    if step == "done":
        step, data = "", {}
    if not step:
        extracted = _extract_fields_from_message(text)
        for field in COLLECTION_ORDER:
            value = extracted.get(field)
            if value and _validate_field(field, value) is None:
                data[field] = _normalize_value(field, value)
        for field in COLLECTION_ORDER:
            if field not in data:
                return {"collection_step": field, "reservation_data": data, "response": _next_prompt(field, data)}
        return {"collection_step": "confirm", "reservation_data": data, "response": _build_summary(data)}
    if step in COLLECTION_ORDER:
        error = _validate_field(step, text)
        if error:
            return {"collection_step": step, "reservation_data": data, "response": f"{error}\n\n{_next_prompt(step, data)}"}
        data[step] = _normalize_value(step, text)
        idx = COLLECTION_ORDER.index(step)
        if idx + 1 < len(COLLECTION_ORDER):
            next_step = COLLECTION_ORDER[idx + 1]
            return {"collection_step": next_step, "reservation_data": data, "response": _next_prompt(next_step, data)}
        return {"collection_step": "confirm", "reservation_data": data, "response": _build_summary(data)}
    if step == "confirm" and text.lower() in ("confirm", "yes", "ok", "y"):
        return {
            "collection_step": "done",
            "reservation_data": data,
            "response": "Reservation details collected. Stage 1 stops here; no administrator approval is included.",
        }
    return {"collection_step": "confirm", "reservation_data": data, "response": _build_summary(data)}


def output_guardrail_node(state: dict) -> dict:
    response = state.get("response", "")
    return {"response": get_output_filter().clean(response)} if response else {}
