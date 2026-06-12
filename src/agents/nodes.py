from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from src.config import DIAL_API_KEY, DIAL_ENDPOINT, DIAL_API_VERSION, DIAL_LLM_DEPLOYMENT, RETRIEVER_K
from src.rag.vectorstore import get_vectorstore, get_embeddings
from src.rag.semantic_cache import get_semantic_cache
from src.database.queries import get_availability_summary, get_pricing_summary, get_hours_summary
from src.guardrails.filters import get_input_filter, get_output_filter
from src.agents.state import ReservationState
import json
import re
from datetime import datetime, timezone, timedelta

_llm: AzureChatOpenAI | None = None

COLLECTION_ORDER = ["name", "surname", "car_number", "start_datetime", "end_datetime", "space_type"]

SPACE_RATES = {"regular": 3.0, "ev_charging": 5.0, "vip": 8.0, "handicapped": 2.0}

# ── Field validation ──────────────────────────────────────────────────────────

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
_NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' \-]{1,60}$")
_CAR_RE = re.compile(r"^[A-Z0-9][A-Z0-9 \-]{1,14}$", re.IGNORECASE)
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.IGNORECASE)


def _parse_time(s: str) -> str | None:
    """Parse a time string to HH:MM. Returns None if unrecognised."""
    m = _TIME_RE.match(s.strip())
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
    """
    Parse natural-language datetime into 'YYYY-MM-DD HH:MM'.
    Accepts:
      - 'YYYY-MM-DD HH:MM'
      - '9am' / '14:00' / '9:30'         (time only → today's date)
      - 'today 9am' / 'today for 9am'    (leading date word)
      - '9am today' / '9am today only'   (trailing date word)
      - 'tomorrow 9am' / '9am tomorrow'
    Returns None if unparseable.
    """
    v = value.strip()
    if _DATETIME_RE.match(v):
        return v

    today = datetime.now(timezone.utc).date()
    v_lower = v.lower()

    if v_lower.startswith("tomorrow"):
        date = today + timedelta(days=1)
        remainder = v_lower[8:].strip()
    elif v_lower.startswith("today"):
        date = today
        remainder = v_lower[5:].strip()
    elif v_lower.endswith("tomorrow"):
        date = today + timedelta(days=1)
        remainder = v_lower[:-8].strip().rstrip(" ,.")
    elif v_lower.endswith("today"):
        date = today
        remainder = v_lower[:-5].strip().rstrip(" ,.")
    else:
        date = today
        remainder = v_lower

    # Strip connecting words: "for 9am", "at 9am", "only 9am"
    for word in ("for ", "at ", "only "):
        if remainder.startswith(word):
            remainder = remainder[len(word):]
            break
    # Strip trailing noise iteratively: "9am today only" → "9am today" → "9am"
    _TRAILING = (" only.", " only", " today", " tomorrow", ".")
    changed = True
    while changed:
        changed = False
        for suffix in _TRAILING:
            if remainder.endswith(suffix):
                remainder = remainder[:-len(suffix)].strip()
                changed = True
                break

    time_str = _parse_time(remainder)
    if time_str is None:
        return None
    return f"{date.strftime('%Y-%m-%d')} {time_str}"


def _validate_field(step: str, value: str) -> str | None:
    """Return an error message string if invalid, else None."""
    v = value.strip()
    if not v:
        return "This field cannot be empty. Please try again."
    if len(v) > 200:
        return "That response is too long. Please enter a shorter value."
    if step in ("name", "surname"):
        if not _NAME_RE.match(v):
            return "Please enter a valid name (letters, spaces, hyphens only — max 60 chars)."
    elif step == "car_number":
        if not _CAR_RE.match(v):
            return "Invalid format. Please use a standard plate, e.g. MH04AB1234 or ABC-1234."
    elif step in ("start_datetime", "end_datetime"):
        if _parse_datetime(v) is None:
            return "I couldn't read that time. Try: today 9am, tomorrow 14:00, or 2026-06-15 09:00."
    elif step == "space_type":
        if v.lower() not in SPACE_RATES:
            return "Please choose one of: regular, ev_charging, vip, or handicapped."
    return None


def _normalize_value(step: str, value: str) -> str:
    """Return the canonical stored value (normalises datetimes; strips others)."""
    if step in ("start_datetime", "end_datetime"):
        parsed = _parse_datetime(value.strip())
        return parsed if parsed else value.strip()
    return value.strip()


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


# ---------- INPUT GUARDRAIL ----------

def input_guardrail_node(state: ReservationState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    is_blocked, reason = get_input_filter().check(last_msg)
    if is_blocked:
        return {
            "guardrail_blocked": True,
            "response": f"I'm sorry, I cannot process that request. {reason} "
                        "Please ask me about parking information or making a reservation.",
        }
    return {"guardrail_blocked": False}


# ---------- INTENT DETECTION ----------

def intent_detection_node(state: ReservationState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    collection_step = state.get("collection_step", "")

    if collection_step and collection_step not in ("", "done"):
        return {"intent": "reservation"}

    # Always route cancel/stop commands to reservation_node so it can handle them cleanly
    if last_msg.strip().lower() in ("cancel", "stop", "quit", "exit", "no"):
        return {"intent": "reservation"}

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=(
            "Classify the user's intent. Reply with ONLY one word — no punctuation, no explanation:\n"
            "- info_query: asking about parking info (location, prices, hours, availability, rules, features, FAQ)\n"
            "- reservation: wants to make, book, or reserve a parking space\n"
            "- unknown: completely unrelated to parking"
        )),
        HumanMessage(content=last_msg),
    ])

    intent = response.content.strip().lower().split()[0]
    if intent not in ("info_query", "reservation", "unknown"):
        intent = "info_query"

    return {"intent": intent}


# ---------- RAG NODE ----------

def rag_node(state: ReservationState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    # Embed once — reused for both cache lookup and vector search
    embeddings_model = get_embeddings()
    query_embedding = embeddings_model.embed_query(last_msg)

    # Semantic cache check — skip LLM + ChromaDB on hit
    cache = get_semantic_cache()
    cached = cache.lookup(query_embedding)
    if cached is not None:
        return {"retrieved_context": "", "response": cached}

    # Cache miss — search ChromaDB reusing the pre-computed embedding
    vs = get_vectorstore()
    docs = vs.similarity_search_by_vector(query_embedding, k=RETRIEVER_K)
    rag_context = "\n\n---\n\n".join(doc.page_content for doc in docs)

    dynamic_context = "\n".join([
        get_availability_summary(),
        "",
        get_pricing_summary(),
        "",
        get_hours_summary(),
    ])

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=(
            "You are a helpful and friendly assistant for CityPark Premium Parking.\n"
            "For casual greetings or small talk (e.g. 'how are you', 'hi', 'thanks'), respond naturally "
            "and briefly — you don't need to force a parking angle.\n"
            "For parking questions, answer based on the context below; be concise and clear. "
            "If a parking question isn't answered by the context, say so and suggest contacting reception.\n\n"
            f"KNOWLEDGE BASE:\n{rag_context}\n\n"
            f"LIVE DATA:\n{dynamic_context}"
        )),
        HumanMessage(content=last_msg),
    ])

    cache.store(query_embedding, response.content, last_msg)
    return {
        "retrieved_context": rag_context,
        "response": response.content,
    }


# ---------- RESERVATION NODE ----------

def _extract_fields_from_message(msg: str) -> dict:
    """Use LLM to extract any reservation fields the user mentioned in their opening message."""
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=(
            "Extract parking reservation details from the user's message. "
            "Return ONLY a valid JSON object with these keys: "
            "name, surname, car_number, start_datetime, end_datetime, space_type. "
            "Use null for any field not clearly provided as an actual value. "
            "IMPORTANT: name and surname must be real personal names (single words, letters only). "
            "If the user says 'my name is X' or 'I am X', X is the name. "
            "Do NOT extract a full sentence as a name. If unsure, use null. "
            "For start_datetime and end_datetime, always use EXACTLY one of these formats: "
            "'today HH:MM', 'tomorrow HH:MM', or 'YYYY-MM-DD HH:MM' (24-hour clock). "
            "Examples: 'today 06:00', 'today 18:00', 'tomorrow 09:30', '2026-06-15 14:00'. "
            "Never include words like 'for', 'only', 'at', 'until' in the datetime value. "
            "Example output: {\"name\": \"John\", \"surname\": \"Doe\", \"car_number\": null, "
            "\"start_datetime\": \"today 06:00\", \"end_datetime\": \"today 18:00\", \"space_type\": \"vip\"}"
        )),
        HumanMessage(content=msg),
    ])
    try:
        raw = response.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        result = {}
        for k, v in data.items():
            if not v or not isinstance(v, str) or not v.strip():
                continue
            # Sanity-check: name/surname must look like a real name (letters only, max 3 words)
            if k in ("name", "surname"):
                words = v.strip().split()
                if len(words) > 3 or not all(re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-]+$", w) for w in words):
                    continue
            result[k] = v.strip()
        return result
    except Exception:
        return {}


def _get_skip_fields(user_profile: dict) -> set:
    """Return COLLECTION_ORDER steps to skip when the user profile has complete identity data."""
    if (user_profile.get("first_name") and user_profile.get("last_name")
            and user_profile.get("car_number")):
        return {"name", "surname", "car_number"}
    return set()


def _preprocess_datetime_msg(msg: str) -> str:
    """Strip leading keywords and take only the relevant date/time part."""
    v = msg.strip()
    for prefix in ("start at ", "end at ", "starting at ", "ending at ",
                   "start ", "end ", "from ", "to ", "at ", "on "):
        if v.lower().startswith(prefix):
            v = v[len(prefix):]
            break
    # If "X and Y", take only the first part (handles "9am today and end tomorrow")
    if " and " in v.lower():
        v = v.lower().split(" and ")[0].strip()
    return v


def reservation_node(state: ReservationState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content.strip() if messages else ""
    step = state.get("collection_step", "")
    reservation_data = dict(state.get("reservation_data") or {})
    user_profile = state.get("user_profile") or {}
    skip_fields = _get_skip_fields(user_profile)

    if last_msg.lower() in ("cancel", "stop", "quit", "exit", "no"):
        return {
            "collection_step": "",
            "reservation_data": {},
            "response": "Reservation cancelled. Is there anything else I can help you with?",
        }

    # Reset completed/stuck steps so users can make a new reservation
    if step in ("done", "pending_approval"):
        step = ""
        reservation_data = {}

    if not step:
        # ── Step 1: pre-fill identity from logged-in profile ──────────────────
        pre_data = {}
        if skip_fields:
            pre_data = {
                "name": user_profile["first_name"],
                "surname": user_profile["last_name"],
                "car_number": user_profile["car_number"],
            }

        # ── Step 2: extract remaining fields from the opening message ─────────
        extracted = _extract_fields_from_message(last_msg)
        for field in COLLECTION_ORDER:
            if field in pre_data:
                continue  # already set from profile
            val = extracted.get(field, "")
            if not val:
                continue
            # Preprocess datetime values before validating
            if field in ("start_datetime", "end_datetime"):
                val = _preprocess_datetime_msg(val)
            if not _validate_field(field, val):
                pre_data[field] = _normalize_value(field, val)

        # ── Step 3: find first missing field ──────────────────────────────────
        next_step = None
        for field in COLLECTION_ORDER:
            if field not in pre_data:
                next_step = field
                break

        # ── All fields collected → straight to confirm ─────────────────────
        if next_step is None:
            if skip_fields:
                intro = (
                    f"Got it, {pre_data['name']}! I've pre-filled your identity and picked up "
                    f"everything else from your message.\n\n"
                )
            else:
                intro = "Got it — here's a summary of your reservation:\n\n"
            return {
                "collection_step": "confirm",
                "reservation_data": pre_data,
                "response": intro + _build_summary(pre_data),
            }

        # ── Some fields missing → build greeting and ask for next field ───────
        name = pre_data.get("name") or (user_profile.get("first_name") if skip_fields else None)
        if name:
            greeting = f"Sure, {name}! "
        else:
            greeting = ""

        return {
            "collection_step": next_step,
            "reservation_data": pre_data,
            "response": greeting + _next_prompt(next_step, pre_data),
        }

    if step in COLLECTION_ORDER:
        # For datetime steps, preprocess to strip leading keywords and "X and end Y" patterns
        if step in ("start_datetime", "end_datetime"):
            processed_msg = _preprocess_datetime_msg(last_msg)
        else:
            processed_msg = last_msg

        # "today" / "tomorrow" alone for datetime — date is known, ask for time
        if step in ("start_datetime", "end_datetime") and processed_msg.lower().strip() in ("today", "tomorrow"):
            day_label = processed_msg.lower().strip()
            return {
                "collection_step": step,
                "reservation_data": reservation_data,
                "response": f"Got it — {day_label}! What time? (e.g. 9am, 14:00, 6:30pm)",
            }

        # Detect confused / off-topic input and respond helpfully via LLM
        error = _validate_field(step, processed_msg)
        if error and len(processed_msg.split()) >= 2:
            llm = get_llm()
            field_hint = _next_prompt(step, reservation_data)
            helpful = llm.invoke([
                SystemMessage(content=(
                    "You are a friendly parking reservation assistant mid-way through collecting booking details. "
                    "The user has sent something unexpected. Briefly and warmly explain what you need, "
                    "using the hint below. Do not repeat the hint verbatim — rephrase it naturally. "
                    "Keep it to 2 sentences maximum.\n\n"
                    f"What you need next:\n{field_hint}"
                )),
                HumanMessage(content=last_msg),
            ])
            return {
                "collection_step": step,
                "reservation_data": reservation_data,
                "response": helpful.content,
            }

        if error:
            prompt = _next_prompt(step, reservation_data) if step != COLLECTION_ORDER[0] else "What is your first name?"
            return {
                "collection_step": step,
                "reservation_data": reservation_data,
                "response": f"{error}\n\n{prompt}",
            }
        reservation_data[step] = _normalize_value(step, processed_msg)
        idx = COLLECTION_ORDER.index(step)

        if idx + 1 < len(COLLECTION_ORDER):
            next_step = COLLECTION_ORDER[idx + 1]
            return {
                "collection_step": next_step,
                "reservation_data": reservation_data,
                "response": _next_prompt(next_step, reservation_data),
            }
        else:
            return {
                "collection_step": "confirm",
                "reservation_data": reservation_data,
                "response": _build_summary(reservation_data),
            }

    if step == "confirm":
        if last_msg.lower() in ("confirm", "yes", "ok", "proceed", "y", "sure"):
            return {
                "collection_step": "pending_approval",
                "reservation_data": reservation_data,
                "response": (
                    "Thank you! Your reservation details have been recorded.\n"
                    "Sending your request to our administrator for approval now..."
                ),
            }
        else:
            return {
                "collection_step": "confirm",
                "reservation_data": reservation_data,
                "response": _build_summary(reservation_data) + "\n\nType 'confirm' to submit or 'cancel' to start over.",
            }

    return {"response": "Something went wrong. Please type 'cancel' and try again."}


def _next_prompt(step: str, data: dict) -> str:
    name = data.get("name", "")
    prompts = {
        "name": "What's your first name?",
        "surname": f"Nice to meet you{', ' + name if name else ''}! What's your surname?",
        "car_number": "What's your car plate number? (e.g. ABC-1234 or MH04AB1234)",
        "start_datetime": "When would you like to start? (e.g. today 9am, tomorrow 14:00, 2026-06-15 09:00)",
        "end_datetime": "And when should it end? (e.g. today 6pm, tomorrow 18:00)",
        "space_type": "What type of space? regular ($3/hr) · ev_charging ($5/hr) · vip ($8/hr) · handicapped ($2/hr)",
    }
    return prompts.get(step, "Please provide the next detail.")


def _build_summary(data: dict) -> str:
    space_type = data.get("space_type", "regular").lower().strip()
    rate = SPACE_RATES.get(space_type, 3.0)
    return (
        "Reservation Summary:\n"
        "--------------------\n"
        f"Name:        {data.get('name', 'N/A')} {data.get('surname', 'N/A')}\n"
        f"Car Number:  {data.get('car_number', 'N/A')}\n"
        f"Start:       {data.get('start_datetime', 'N/A')}\n"
        f"End:         {data.get('end_datetime', 'N/A')}\n"
        f"Space Type:  {space_type.replace('_', ' ').title()}\n"
        f"Rate:        ${rate:.2f}/hour\n"
        "--------------------\n\n"
        "Type 'confirm' to submit your request or 'cancel' to start over."
    )


# ---------- ADMIN AGENT NODE ----------

def admin_agent_node(state: ReservationState, config: RunnableConfig) -> dict:
    from src.admin.agent import run_admin_agent
    from src.database.queries import link_user_to_reservation
    messages = state.get("messages", [])
    reservation_data = dict(state.get("reservation_data") or {})
    user_profile = state.get("user_profile") or {}

    # Extract thread_id correctly from LangGraph RunnableConfig
    thread_id = (config or {}).get("configurable", {}).get("thread_id", "unknown-thread")

    # Run admin agent: saves to DB + sends notification
    reservation_id = run_admin_agent(thread_id, reservation_data)

    # Attach logged-in user_id so approval notifications can be delivered
    user_id = user_profile.get("user_id")
    if user_id and reservation_id:
        try:
            link_user_to_reservation(reservation_id, user_id)
        except Exception as e:
            print(f"[admin_agent_node] Failed to link user_id: {e}")

    # Suspend graph — wait for admin to approve/reject via FastAPI
    admin_response = interrupt({
        "reservation_id": reservation_id,
        "message": "Waiting for administrator approval...",
    })

    decision = admin_response.get("decision", "rejected") if isinstance(admin_response, dict) else "rejected"
    notes = admin_response.get("notes", "") if isinstance(admin_response, dict) else ""

    if decision == "approved":
        response = (
            "Great news! Your reservation has been APPROVED by our administrator.\n\n"
            f"Reservation ID: {reservation_id[:8].upper()}\n"
            "Please keep this ID for your records. See you at CityPark!\n\n"
            "Is there anything else I can help you with?"
        )
    else:
        response = (
            "We're sorry, your reservation request was not approved by our administrator.\n"
            f"{('Reason: ' + notes) if notes else ''}\n\n"
            "Please try a different time slot or contact us at +1 (555) 123-4567 for assistance."
        )

    return {
        "collection_step": "done",
        "reservation_id": reservation_id,
        "approval_status": decision,
        "response": response,
    }


# ---------- OUTPUT GUARDRAIL ----------

def output_guardrail_node(state: ReservationState) -> dict:
    response = state.get("response", "")
    if not response:
        return {}
    clean = get_output_filter().clean(response)
    return {"response": clean}
