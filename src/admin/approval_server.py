import hmac
import json as _json
import threading
import time
import uuid as _uuid_mod
import uvicorn
from collections import defaultdict
from html import escape as _esc
from fastapi import FastAPI, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from src.config import ADMIN_SECRET_TOKEN, APPROVAL_SERVER_PORT, SESSION_COOKIE_NAME, SESSION_TTL_DAYS
from src.database.queries import (
    approve_reservation, reject_reservation, get_pending_reservations, get_all_reservations, get_reservation,
    get_user_by_email, create_user, verify_password, create_session,
    get_session_user, invalidate_session, update_last_login,
    save_chat_message, get_chat_messages, get_thread_title,
    get_user_chat_sessions, create_notification,
    get_user_notifications, get_unread_count, mark_notifications_read,
)

app = FastAPI(title="CityPark Admin Approval Server")

# ── Security headers middleware ───────────────────────────────────────────────

@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# ── Live metrics ──────────────────────────────────────────────────────────────
_metrics_start = time.time()
_req_count: dict = defaultdict(int)
_req_success: dict = defaultdict(int)
_req_latency: dict = defaultdict(float)
_metrics_lock = threading.Lock()


@app.middleware("http")
async def _track_metrics(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - t0
    path = request.url.path
    with _metrics_lock:
        _req_count[path] += 1
        if response.status_code < 400:
            _req_success[path] += 1
        _req_latency[path] += elapsed
    return response


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000,
                         description="User message — max 2000 characters")
    thread_id: str = Field(..., min_length=36, max_length=36,
                           description="UUID v4 thread identifier")

# Injected by main.py after graph is built
_graph_app = None
_graph_config_factory = None


def set_graph(graph_app, config_factory):
    global _graph_app, _graph_config_factory
    _graph_app = graph_app
    _graph_config_factory = config_factory


def _write_to_mcp(record) -> None:
    try:
        from src.mcp_server.client import call_mcp_write
        result = call_mcp_write(
            reservation_id=record.reservation_id,
            name=record.name,
            surname=record.surname,
            car_number=record.car_number,
            start_datetime=record.start_datetime,
            end_datetime=record.end_datetime,
            space_type=record.space_type,
        )
        print(f"[ApprovalServer] MCP write result: {result}")
    except Exception as e:
        print(f"[ApprovalServer] MCP write failed (non-critical): {e}")


def _resume_graph(thread_id: str, decision: str, notes: str = "",
                  reservation_id: str = "") -> None:
    if _graph_app is None:
        return
    try:
        from langgraph.types import Command
        config = _graph_config_factory(thread_id)
        _graph_app.invoke(Command(resume={"decision": decision, "notes": notes}), config=config)
    except Exception as e:
        print(f"[ApprovalServer] Graph resume error: {e}")

    if reservation_id:
        record = get_reservation(reservation_id)
        if record and getattr(record, "user_id", None):
            short_id = reservation_id[:8].upper()
            if decision == "approved":
                msg = (f"Your parking reservation {short_id} has been APPROVED! "
                       "Check your dashboard for details.")
                ntype = "approved"
            else:
                reason = f" Reason: {notes}" if notes else ""
                msg = f"Your parking reservation {short_id} was not approved.{reason}"
                ntype = "rejected"
            try:
                create_notification(
                    user_id=record.user_id,
                    reservation_id=reservation_id,
                    message=msg,
                    notification_type=ntype,
                )
            except Exception as e:
                print(f"[ApprovalServer] Notification creation error: {e}")


def _auth(token: str) -> None:
    """Constant-time token comparison to prevent timing-based side-channel attacks."""
    if not hmac.compare_digest(token, ADMIN_SECRET_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid token")


def _get_current_user(request: Request):
    """Read session cookie and return User object, or None for guests."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return get_session_user(token)


# ── Chat UI ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def chat_ui(request: Request):
    user = _get_current_user(request)
    return _chat_page(user=user)


@app.post("/chat")
def chat_endpoint(req: ChatRequest, request: Request):
    if _graph_app is None:
        raise HTTPException(status_code=503, detail="Chat not ready")
    try:
        _uuid_mod.UUID(req.thread_id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid thread_id: must be a UUID v4")

    user = _get_current_user(request)
    user_profile = {}
    if user:
        user_profile = {
            "user_id": user.user_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "car_number": user.car_number or "",
        }

    # Save user message; set chat_title on first message of the thread
    existing_title = get_thread_title(req.thread_id)
    chat_title = existing_title or req.message[:80]
    try:
        save_chat_message(
            thread_id=req.thread_id,
            role="user",
            content=req.message,
            user_id=user.user_id if user else None,
            chat_title=chat_title if not existing_title else None,
        )
    except Exception:
        pass

    from langchain_core.messages import HumanMessage
    config = _graph_config_factory(req.thread_id)
    try:
        result = _graph_app.invoke(
            {"messages": [HumanMessage(content=req.message)], "user_profile": user_profile},
            config=config,
        )
        response = result.get("response", "Something went wrong. Please try again.")
    except Exception as e:
        if "interrupt" in str(e).lower() or "NodeInterrupt" in type(e).__name__:
            response = (
                "Your reservation has been submitted and is awaiting administrator approval. "
                "You will be notified once a decision is made."
            )
        else:
            response = "An error occurred. Please try again."

    try:
        save_chat_message(
            thread_id=req.thread_id,
            role="assistant",
            content=response,
            user_id=user.user_id if user else None,
        )
    except Exception:
        pass

    return {"response": response, "thread_id": req.thread_id}


# ── User Auth ─────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(error: str = Query(default=""), mode: str = Query(default="login")):
    return _login_register_page(error=error, mode=mode)


@app.post("/auth/login")
def do_login(request: Request, email: str = Form(...), password: str = Form(...)):
    user = get_user_by_email(email.lower().strip())
    if not user or not verify_password(user, password):
        return RedirectResponse(url="/login?error=Invalid+email+or+password.", status_code=303)

    token = create_session(user.user_id)
    update_last_login(user.user_id)

    if user.role == "admin":
        redirect_url = f"/admin/dashboard?token={ADMIN_SECRET_TOKEN}"
    else:
        redirect_url = "/dashboard"

    resp = RedirectResponse(url=redirect_url, status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="strict",
    )
    return resp


@app.post("/auth/register")
def do_register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    car_number: str = Form(default=""),
):
    email = email.lower().strip()
    if get_user_by_email(email):
        return RedirectResponse(
            url="/login?mode=register&error=An+account+with+that+email+already+exists.",
            status_code=303,
        )
    if len(password) < 8:
        return RedirectResponse(
            url="/login?mode=register&error=Password+must+be+at+least+8+characters.",
            status_code=303,
        )
    if not first_name.strip() or not last_name.strip():
        return RedirectResponse(
            url="/login?mode=register&error=First+and+last+name+are+required.",
            status_code=303,
        )
    create_user(
        email=email,
        password=password,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        car_number=car_number.strip() or None,
        role="user",
    )
    user = get_user_by_email(email)
    token = create_session(user.user_id)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="strict",
    )
    return resp


@app.post("/auth/logout")
def do_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        invalidate_session(token)
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


# ── User Dashboard ────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def user_dashboard(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    notifications = get_user_notifications(user.user_id)
    # Get user's reservations
    from src.database.models import get_session as _db_session
    from src.database.models import Reservation
    db = _db_session()
    reservations = db.query(Reservation).filter(
        Reservation.user_id == user.user_id
    ).order_by(Reservation.id.desc()).all()
    db.close()
    return _user_dashboard_page(user=user, reservations=reservations, notifications=notifications)


# ── Chat API ──────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def api_sessions(request: Request):
    user = _get_current_user(request)
    if not user:
        return []
    return get_user_chat_sessions(user.user_id)


@app.get("/api/messages/{thread_id}")
def api_messages(thread_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        return []
    msgs = get_chat_messages(thread_id)
    # Security: only return messages belonging to this user
    return [
        {"role": m.role, "content": m.content, "created_at": m.created_at}
        for m in msgs
        if m.user_id == user.user_id
    ]


@app.get("/api/notifications")
def api_notifications(request: Request):
    user = _get_current_user(request)
    if not user:
        return {"unread_count": 0, "notifications": []}
    notes = get_user_notifications(user.user_id)
    unread = sum(1 for n in notes if not n.is_read)
    return {
        "unread_count": unread,
        "notifications": [
            {
                "notification_id": n.notification_id,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at,
                "notification_type": n.notification_type,
            }
            for n in notes
        ],
    }


@app.post("/api/notifications/read")
def api_mark_read(request: Request):
    user = _get_current_user(request)
    if user:
        mark_notifications_read(user.user_id)
    return {"ok": True}


# ── Admin Portal ──────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
def admin_login_page():
    return RedirectResponse(url="/login", status_code=302)


@app.post("/admin/login", response_class=HTMLResponse)
def admin_login(token: str = Form(...)):
    if not hmac.compare_digest(token, ADMIN_SECRET_TOKEN):
        return RedirectResponse(url="/admin?error=Invalid+token.+Please+try+again.", status_code=303)
    return RedirectResponse(url=f"/admin/dashboard?token={token}", status_code=303)


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(token: str = Query(...), tab: str = Query(default="pending")):
    _auth(token)
    if tab == "history":
        records = get_all_reservations()
    else:
        records = get_pending_reservations()
    return _admin_dashboard_page(token=token, records=records, tab=tab)


@app.get("/approve/{reservation_id}", response_class=HTMLResponse)
def approve(reservation_id: str, token: str = Query(...)):
    _auth(token)
    record = get_reservation(reservation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if record.status != "pending":
        return _action_result_page(
            "Already Processed",
            f"Reservation {reservation_id[:8].upper()} is already <strong>{record.status}</strong>.",
            "#888888",
            token,
        )
    approve_reservation(reservation_id)
    _resume_graph(record.thread_id, "approved", reservation_id=reservation_id)
    _write_to_mcp(record)
    return _action_result_page(
        "Reservation Approved",
        f"Reservation <strong>{_esc(reservation_id[:8].upper())}</strong> for "
        f"<strong>{_esc(record.name)} {_esc(record.surname)}</strong> has been approved successfully.",
        "#27ae60",
        token,
    )


@app.get("/reject/{reservation_id}", response_class=HTMLResponse)
def reject(
    reservation_id: str,
    token: str = Query(...),
    notes: str = Query(default="Rejected by administrator."),
):
    _auth(token)
    record = get_reservation(reservation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if record.status != "pending":
        return _action_result_page(
            "Already Processed",
            f"Reservation {reservation_id[:8].upper()} is already <strong>{record.status}</strong>.",
            "#888888",
            token,
        )
    reject_reservation(reservation_id, notes)
    _resume_graph(record.thread_id, "rejected", notes, reservation_id=reservation_id)
    return _action_result_page(
        "Reservation Rejected",
        f"Reservation <strong>{reservation_id[:8].upper()}</strong> for "
        f"<strong>{record.name} {record.surname}</strong> has been rejected.",
        "#e74c3c",
        token,
    )


@app.get("/pending")
def pending_reservations(token: str = Query(...)):
    _auth(token)
    records = get_pending_reservations()
    return [
        {
            "reservation_id": r.reservation_id,
            "name": f"{r.name} {r.surname}",
            "car_number": r.car_number,
            "start": r.start_datetime,
            "end": r.end_datetime,
            "space_type": r.space_type,
            "submitted_at": r.submitted_at,
        }
        for r in records
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics(token: str = Query(...)):
    _auth(token)
    uptime = round(time.time() - _metrics_start, 1)
    endpoints = {}
    with _metrics_lock:
        for path, total in _req_count.items():
            success = _req_success[path]
            avg_ms = round(_req_latency[path] / total * 1000, 2) if total else 0
            endpoints[path] = {
                "total_requests": total,
                "success_rate": f"{success / total * 100:.1f}%" if total else "N/A",
                "avg_latency_ms": avg_ms,
            }
    try:
        from src.rag.semantic_cache import get_semantic_cache
        cache_stats = get_semantic_cache().stats()
    except Exception:
        cache_stats = {}
    return {
        "uptime_seconds": uptime,
        "total_requests": sum(_req_count.values()),
        "endpoints": endpoints,
        "semantic_cache": cache_stats,
    }


# ── HTML Page Builders ────────────────────────────────────────────────────────

_BASE_STYLE = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; min-height: 100vh; }
  header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
    color: white; padding: 16px 28px; display: flex; align-items: center; gap: 14px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }
  .logo { width: 44px; height: 44px; background: #e94560; border-radius: 10px;
    display: flex; align-items: center; justify-content: center; font-size: 20px;
    font-weight: bold; flex-shrink: 0; }
  .header-text h1 { font-size: 18px; font-weight: 700; }
  .header-text p { font-size: 12px; color: #a0aec0; margin-top: 2px; }
  .header-actions { margin-left: auto; display: flex; gap: 10px; align-items: center; }
  .nav-link {
    color: rgba(255,255,255,0.75); text-decoration: none; font-size: 13px;
    padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2);
    transition: all 0.2s;
  }
  .nav-link:hover { background: rgba(255,255,255,0.1); color: white; }
"""


def _admin_login_page(error: str = "") -> str:
    error_html = (
        f'<div class="error-msg">{_esc(error)}</div>' if error else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CityPark &mdash; Admin Login</title>
  <style>
    {_BASE_STYLE}
    .container {{
      display: flex; align-items: center; justify-content: center;
      min-height: calc(100vh - 68px); padding: 40px 20px;
    }}
    .card {{
      background: white; border-radius: 16px; padding: 40px 44px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10); width: 100%; max-width: 420px;
    }}
    .card h2 {{ font-size: 22px; color: #1a1a2e; margin-bottom: 6px; }}
    .card .subtitle {{ font-size: 13px; color: #718096; margin-bottom: 28px; }}
    label {{ display: block; font-size: 13px; font-weight: 600; color: #4a5568; margin-bottom: 6px; }}
    input[type="password"] {{
      width: 100%; padding: 11px 14px; border: 1.5px solid #e2e8f0; border-radius: 8px;
      font-size: 14px; outline: none; transition: border-color 0.2s; margin-bottom: 20px;
    }}
    input[type="password"]:focus {{ border-color: #0f3460; }}
    button[type="submit"] {{
      width: 100%; background: #0f3460; color: white; border: none;
      padding: 12px; border-radius: 8px; font-size: 15px; font-weight: 600;
      cursor: pointer; transition: background 0.2s;
    }}
    button[type="submit"]:hover {{ background: #e94560; }}
    .error-msg {{
      background: #fff5f5; border: 1px solid #fed7d7; color: #c53030;
      padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 18px;
    }}
    .footer-note {{ text-align: center; margin-top: 24px; font-size: 12px; color: #a0aec0; }}
    .chat-link {{ display: block; text-align: center; margin-top: 14px; font-size: 13px; color: #0f3460; text-decoration: none; }}
    .chat-link:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
<header>
  <div class="logo">P</div>
  <div class="header-text">
    <h1>CityPark Premium Parking</h1>
    <p>Administrator Portal</p>
  </div>
  <div class="header-actions"></div>
</header>
<div class="container">
  <div class="card">
    <h2>&#x1F512; Admin Login</h2>
    <p class="subtitle">Enter your administrator token to access the reservation dashboard.</p>
    {error_html}
    <form method="POST" action="/admin/login">
      <label for="token">Administrator Token</label>
      <input type="password" id="token" name="token" placeholder="Enter admin token..." required autofocus />
      <button type="submit">Sign In &rarr;</button>
    </form>
    <p class="footer-note">Access is restricted to authorised CityPark administrators only.</p>
  </div>
</div>
</body>
</html>"""


def _admin_dashboard_page(token: str, records: list, tab: str = "pending") -> str:
    pending_count = sum(1 for r in records if r.status == "pending") if tab == "history" else len(records)
    all_count = len(records) if tab == "history" else None
    badge_color = "#e74c3c" if pending_count > 0 else "#27ae60"
    badge_text = f"{pending_count} Pending" if pending_count > 0 else "All Clear"

    def _fmt_dt(val):
        if not val:
            return "—"
        try:
            return val[:16].replace("T", " ")
        except Exception:
            return str(val)[:16]

    if tab == "history":
        # History tab — all reservations with status + reviewed_at
        if not records:
            rows_html = '<tr><td colspan="9" style="text-align:center;padding:40px;color:#a0aec0;font-size:14px;">&#x1F4CB; No reservations yet.</td></tr>'
        else:
            status_colors = {"approved": "#27ae60", "pending": "#f39c12", "rejected": "#e74c3c"}
            rows = []
            for r in records:
                short_id = _esc(r.reservation_id[:8].upper())
                full_name_html = _esc(f"{r.name} {r.surname}")
                sc = status_colors.get(r.status, "#718096")
                space_cls = _esc(r.space_type)
                space_label = _esc(r.space_type.replace("_", " ").title())
                submitted = _fmt_dt(r.submitted_at)
                reviewed = _fmt_dt(getattr(r, "reviewed_at", None))
                admin_notes = _esc(getattr(r, "admin_notes", "") or "")
                rows.append(f"""
                <tr>
                  <td><span class="res-id">{short_id}</span></td>
                  <td><strong>{full_name_html}</strong></td>
                  <td>{_esc(r.car_number)}</td>
                  <td>{_esc(r.start_datetime)}</td>
                  <td>{_esc(r.end_datetime)}</td>
                  <td><span class="space-badge space-{space_cls}">{space_label}</span></td>
                  <td><span style="color:{sc};font-weight:600;font-size:12px;">{_esc(r.status.upper())}</span></td>
                  <td style="font-size:12px;color:#718096;">{submitted}</td>
                  <td style="font-size:12px;color:#718096;">{reviewed}{('<br><span style="color:#a0aec0;font-size:11px;">' + admin_notes + '</span>') if admin_notes else ''}</td>
                </tr>""")
            rows_html = "\n".join(rows)
        table_html = f"""<table>
          <thead><tr>
            <th>ID</th><th>Customer</th><th>Car</th><th>Start</th><th>End</th>
            <th>Space</th><th>Status</th><th>Submitted</th><th>Reviewed</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table>"""
    else:
        # Pending tab — approve/reject actions
        if not records:
            rows_html = """
            <tr>
              <td colspan="8" style="text-align:center;padding:40px;color:#a0aec0;font-size:14px;">
                &#x2705; No pending reservations. All caught up!
              </td>
            </tr>"""
        else:
            rows = []
            for r in records:
                short_id = _esc(r.reservation_id[:8].upper())
                full_name_html = _esc(f"{r.name} {r.surname}")
                car_html = _esc(r.car_number)
                start_html = _esc(r.start_datetime)
                end_html = _esc(r.end_datetime)
                space_label = _esc(r.space_type.replace("_", " ").title())
                space_cls = _esc(r.space_type)
                submitted = _fmt_dt(r.submitted_at)
                user_tag = '<span style="color:#27ae60;font-size:11px;">&#x1F464; member</span>' if getattr(r, "user_id", None) else '<span style="color:#a0aec0;font-size:11px;">guest</span>'
                js_full_name = _json.dumps(f"{r.name} {r.surname}")
                js_res_id = _json.dumps(r.reservation_id)
                js_token = _json.dumps(token)
                rows.append(f"""
                <tr>
                  <td><span class="res-id">{short_id}</span></td>
                  <td><strong>{full_name_html}</strong><br>{user_tag}</td>
                  <td>{car_html}</td>
                  <td>{start_html}</td>
                  <td>{end_html}</td>
                  <td><span class="space-badge space-{space_cls}">{space_label}</span></td>
                  <td style="font-size:12px;color:#718096;">{submitted}</td>
                  <td class="actions-cell">
                    <a href="/approve/{_esc(r.reservation_id)}?token={_esc(token)}" class="btn-approve"
                       onclick="return confirm('Approve reservation for ' + {js_full_name} + '?')">
                      &#x2714; Approve
                    </a>
                    <a href="#" class="btn-reject"
                       onclick='rejectWithNotes({js_res_id}, {js_token}); return false;'>
                      &#x2718; Reject
                    </a>
                  </td>
                </tr>""")
            rows_html = "\n".join(rows)
        table_html = f"""<table>
          <thead><tr>
            <th>ID</th><th>Customer</th><th>Car Number</th><th>Start</th><th>End</th>
            <th>Space Type</th><th>Submitted</th><th>Actions</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CityPark &mdash; Admin Dashboard</title>
  <style>
    {_BASE_STYLE}
    .page-body {{ padding: 32px 28px; max-width: 1200px; margin: 0 auto; }}
    .page-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
    .page-header h2 {{ font-size: 22px; color: #1a1a2e; }}
    .badge {{
      background: {badge_color}; color: white; font-size: 12px; font-weight: 700;
      padding: 4px 12px; border-radius: 20px; letter-spacing: 0.5px;
    }}
    .refresh-btn {{
      margin-left: auto; background: white; border: 1.5px solid #e2e8f0;
      color: #4a5568; padding: 8px 18px; border-radius: 8px; cursor: pointer;
      font-size: 13px; text-decoration: none; transition: all 0.2s;
    }}
    .refresh-btn:hover {{ border-color: #0f3460; color: #0f3460; }}
    .card {{
      background: white; border-radius: 14px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.07); overflow: hidden;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    thead tr {{ background: #f7f8fc; }}
    thead th {{
      text-align: left; padding: 14px 16px; font-size: 11px; font-weight: 700;
      color: #718096; text-transform: uppercase; letter-spacing: 0.6px;
      border-bottom: 1px solid #e2e8f0;
    }}
    tbody tr {{ border-bottom: 1px solid #f0f2f5; transition: background 0.15s; }}
    tbody tr:last-child {{ border-bottom: none; }}
    tbody tr:hover {{ background: #f7f8fc; }}
    tbody td {{ padding: 14px 16px; color: #2d3748; vertical-align: middle; }}
    .res-id {{
      font-family: monospace; font-size: 12px; background: #edf2f7;
      padding: 3px 7px; border-radius: 4px; color: #4a5568;
    }}
    .space-badge {{
      display: inline-block; padding: 3px 10px; border-radius: 12px;
      font-size: 11px; font-weight: 600;
    }}
    .space-regular    {{ background: #ebf8ff; color: #2b6cb0; }}
    .space-ev_charging {{ background: #f0fff4; color: #276749; }}
    .space-vip        {{ background: #faf5ff; color: #6b46c1; }}
    .space-handicapped {{ background: #fffaf0; color: #c05621; }}
    .actions-cell {{ display: flex; gap: 8px; align-items: center; }}
    .btn-approve, .btn-reject {{
      display: inline-block; padding: 6px 14px; border-radius: 6px;
      font-size: 12px; font-weight: 600; text-decoration: none; cursor: pointer;
      transition: all 0.2s; white-space: nowrap;
    }}
    .btn-approve {{ background: #f0fff4; color: #276749; border: 1.5px solid #9ae6b4; }}
    .btn-approve:hover {{ background: #27ae60; color: white; border-color: #27ae60; }}
    .btn-reject  {{ background: #fff5f5; color: #c53030; border: 1.5px solid #feb2b2; }}
    .btn-reject:hover  {{ background: #e74c3c; color: white; border-color: #e74c3c; }}
    .info-bar {{ display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }}
    .stat-box {{
      background: white; border-radius: 10px; padding: 16px 22px;
      box-shadow: 0 1px 6px rgba(0,0,0,0.06); min-width: 140px;
    }}
    .stat-box .val {{ font-size: 28px; font-weight: 700; color: #1a1a2e; }}
    .stat-box .lbl {{ font-size: 11px; color: #718096; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .modal-overlay {{
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.45); z-index: 999;
      align-items: center; justify-content: center;
    }}
    .modal-overlay.active {{ display: flex; }}
    .modal {{
      background: white; border-radius: 14px; padding: 32px 36px;
      width: 100%; max-width: 420px; box-shadow: 0 8px 40px rgba(0,0,0,0.18);
    }}
    .modal h3 {{ font-size: 18px; color: #1a1a2e; margin-bottom: 8px; }}
    .modal p {{ font-size: 13px; color: #718096; margin-bottom: 18px; }}
    .modal textarea {{
      width: 100%; padding: 10px 14px; border: 1.5px solid #e2e8f0;
      border-radius: 8px; font-size: 13px; resize: vertical; min-height: 80px;
      outline: none; font-family: inherit; transition: border-color 0.2s;
    }}
    .modal textarea:focus {{ border-color: #e74c3c; }}
    .modal-actions {{ display: flex; gap: 10px; margin-top: 18px; justify-content: flex-end; }}
    .modal-cancel {{
      background: #f7f8fc; color: #4a5568; border: 1.5px solid #e2e8f0;
      padding: 9px 20px; border-radius: 8px; cursor: pointer; font-size: 13px;
    }}
    .modal-confirm {{
      background: #e74c3c; color: white; border: none;
      padding: 9px 20px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;
    }}
    .modal-confirm:hover {{ background: #c0392b; }}
  </style>
</head>
<body>
<header>
  <div class="logo">P</div>
  <div class="header-text">
    <h1>CityPark Premium Parking</h1>
    <p>Administrator Dashboard &mdash; Reservation Management</p>
  </div>
  <div class="header-actions">
    <form method="POST" action="/auth/logout" style="margin:0">
      <button type="submit" style="background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.25);color:white;padding:6px 14px;border-radius:20px;cursor:pointer;font-size:13px;">&#x1F512; Logout</button>
    </form>
  </div>
</header>

<div class="page-body">
  <div class="info-bar">
    <div class="stat-box">
      <div class="val">{pending_count}</div>
      <div class="lbl">Pending Approvals</div>
    </div>
  </div>

  <div class="page-header">
    <h2>&#x1F4CB; Reservation Management</h2>
    <span class="badge">{badge_text}</span>
    <div style="margin-left:auto;display:flex;gap:10px;align-items:center;">
      <a href="/admin/dashboard?token={token}&tab=pending"
         style="padding:7px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;
         {'background:#0f3460;color:white;' if tab == 'pending' else 'background:white;color:#4a5568;border:1.5px solid #e2e8f0;'}">
        &#x23F3; Pending
      </a>
      <a href="/admin/dashboard?token={token}&tab=history"
         style="padding:7px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;
         {'background:#0f3460;color:white;' if tab == 'history' else 'background:white;color:#4a5568;border:1.5px solid #e2e8f0;'}">
        &#x1F4DC; History
      </a>
      <a href="/admin/dashboard?token={token}&tab={tab}" class="refresh-btn">&#x21BA; Refresh</a>
    </div>
  </div>

  <div class="card">
    {table_html}
  </div>
</div>

<div class="modal-overlay" id="rejectModal">
  <div class="modal">
    <h3>&#x2718; Reject Reservation</h3>
    <p>Optionally provide a reason for the customer.</p>
    <textarea id="rejectNotes" placeholder="e.g. No availability for requested time slot..."></textarea>
    <div class="modal-actions">
      <button class="modal-cancel" onclick="closeModal()">Cancel</button>
      <button class="modal-confirm" onclick="submitReject()">Confirm Rejection</button>
    </div>
  </div>
</div>

<script>
  let _rejectId = null;
  let _rejectToken = null;

  function rejectWithNotes(reservationId, token) {{
    _rejectId = reservationId;
    _rejectToken = token;
    document.getElementById('rejectNotes').value = '';
    document.getElementById('rejectModal').classList.add('active');
    setTimeout(() => document.getElementById('rejectNotes').focus(), 100);
  }}

  function closeModal() {{
    document.getElementById('rejectModal').classList.remove('active');
    _rejectId = null; _rejectToken = null;
  }}

  function submitReject() {{
    if (!_rejectId) return;
    const notes = document.getElementById('rejectNotes').value.trim() || 'Rejected by administrator.';
    window.location.href = `/reject/${{_rejectId}}?token=${{encodeURIComponent(_rejectToken)}}&notes=${{encodeURIComponent(notes)}}`;
  }}

  document.getElementById('rejectModal').addEventListener('click', function(e) {{
    if (e.target === this) closeModal();
  }});
</script>
</body>
</html>"""


def _action_result_page(title: str, message: str, color: str, token: str) -> str:
    icon = "&#x2705;" if "Approved" in title else ("&#x274C;" if "Rejected" in title else "&#x2139;")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CityPark &mdash; {title}</title>
  <style>
    {_BASE_STYLE}
    .container {{
      display: flex; align-items: center; justify-content: center;
      min-height: calc(100vh - 68px); padding: 40px 20px;
    }}
    .card {{
      background: white; border-radius: 16px; padding: 48px 52px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10); width: 100%;
      max-width: 480px; text-align: center;
    }}
    .icon {{ font-size: 52px; margin-bottom: 18px; }}
    h2 {{ font-size: 24px; color: {color}; margin-bottom: 12px; }}
    p {{ font-size: 15px; color: #4a5568; line-height: 1.6; margin-bottom: 28px; }}
    .btn-back {{
      display: inline-block; background: #0f3460; color: white;
      padding: 11px 28px; border-radius: 8px; text-decoration: none;
      font-size: 14px; font-weight: 600; transition: background 0.2s;
    }}
    .btn-back:hover {{ background: #e94560; }}
  </style>
</head>
<body>
<header>
  <div class="logo">P</div>
  <div class="header-text">
    <h1>CityPark Premium Parking</h1>
    <p>Administrator Portal</p>
  </div>
  <div class="header-actions"></div>
</header>
<div class="container">
  <div class="card">
    <div class="icon">{icon}</div>
    <h2>{title}</h2>
    <p>{message}</p>
    <a href="/admin/dashboard?token={token}" class="btn-back">&#8592; Back to Dashboard</a>
  </div>
</div>
</body>
</html>"""


def _login_register_page(error: str = "", mode: str = "login") -> str:
    error_html = f'<div class="error-msg">{_esc(error)}</div>' if error else ""
    login_active = "active" if mode != "register" else ""
    reg_active = "active" if mode == "register" else ""
    login_display = "none" if mode == "register" else "block"
    reg_display = "block" if mode == "register" else "none"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CityPark &mdash; Sign In</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }}
    .card {{
      background: white; border-radius: 20px; padding: 40px 44px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 460px;
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }}
    .logo {{ width: 44px; height: 44px; background: #e94560; border-radius: 10px;
      display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; color: white; }}
    .brand-text h2 {{ font-size: 18px; color: #1a1a2e; font-weight: 700; }}
    .brand-text p {{ font-size: 12px; color: #718096; }}
    .tabs {{ display: flex; gap: 0; margin-bottom: 28px; border-bottom: 2px solid #e2e8f0; }}
    .tab {{
      flex: 1; padding: 10px; text-align: center; font-size: 14px; font-weight: 600;
      color: #718096; cursor: pointer; border-bottom: 2px solid transparent;
      margin-bottom: -2px; transition: all 0.2s;
    }}
    .tab.active {{ color: #0f3460; border-bottom-color: #0f3460; }}
    .tab:hover {{ color: #0f3460; }}
    .error-msg {{
      background: #fff5f5; border: 1px solid #fed7d7; color: #c53030;
      padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 18px;
    }}
    label {{ display: block; font-size: 12px; font-weight: 600; color: #4a5568; margin-bottom: 5px; }}
    input[type="email"], input[type="password"], input[type="text"] {{
      width: 100%; padding: 11px 14px; border: 1.5px solid #e2e8f0; border-radius: 8px;
      font-size: 14px; outline: none; transition: border-color 0.2s; margin-bottom: 14px;
      font-family: inherit;
    }}
    input:focus {{ border-color: #0f3460; }}
    .row-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .hint {{ font-size: 11px; color: #a0aec0; margin-top: -10px; margin-bottom: 14px; }}
    button[type="submit"] {{
      width: 100%; background: #0f3460; color: white; border: none;
      padding: 13px; border-radius: 8px; font-size: 15px; font-weight: 600;
      cursor: pointer; transition: background 0.2s; margin-top: 4px;
    }}
    button[type="submit"]:hover {{ background: #e94560; }}
    .chat-link {{ display: block; text-align: center; margin-top: 18px; font-size: 13px; color: #718096; text-decoration: none; }}
    .chat-link:hover {{ color: #0f3460; text-decoration: underline; }}
    .divider {{ margin: 16px 0; border: none; border-top: 1px solid #e2e8f0; }}
    .admin-link {{ display: block; text-align: center; font-size: 11px; color: #a0aec0; margin-top: 8px; text-decoration: none; }}
    .admin-link:hover {{ color: #718096; }}
  </style>
</head>
<body>
<div class="card">
  <div class="brand">
    <div class="logo">P</div>
    <div class="brand-text">
      <h2>CityPark Premium Parking</h2>
      <p>Your intelligent parking companion</p>
    </div>
  </div>

  {error_html}

  <div class="tabs">
    <div class="tab {login_active}" id="tab-login" onclick="switchTab('login')">Sign In</div>
    <div class="tab {reg_active}" id="tab-register" onclick="switchTab('register')">Create Account</div>
  </div>

  <!-- Login form -->
  <div id="panel-login" style="display:{login_display}">
    <form method="POST" action="/auth/login">
      <label for="login-email">Email Address</label>
      <input type="email" id="login-email" name="email" placeholder="you@example.com" required autofocus />
      <label for="login-password">Password</label>
      <input type="password" id="login-password" name="password" placeholder="Your password" required />
      <button type="submit">Sign In &rarr;</button>
    </form>
  </div>

  <!-- Register form -->
  <div id="panel-register" style="display:{reg_display}">
    <form method="POST" action="/auth/register">
      <label for="reg-email">Email Address</label>
      <input type="email" id="reg-email" name="email" placeholder="you@example.com" required />
      <label for="reg-password">Password <span style="font-weight:400;color:#a0aec0">(min 8 characters)</span></label>
      <input type="password" id="reg-password" name="password" placeholder="Choose a strong password" required minlength="8" />
      <div class="row-2">
        <div>
          <label for="reg-first">First Name</label>
          <input type="text" id="reg-first" name="first_name" placeholder="Jane" required />
        </div>
        <div>
          <label for="reg-last">Last Name</label>
          <input type="text" id="reg-last" name="last_name" placeholder="Smith" required />
        </div>
      </div>
      <label for="reg-car">Car Registration <span style="font-weight:400;color:#a0aec0">(optional)</span></label>
      <input type="text" id="reg-car" name="car_number" placeholder="e.g. MH04AB1234" />
      <p class="hint">Save time on future reservations — we'll pre-fill this for you.</p>
      <button type="submit">Create Account &rarr;</button>
    </form>
  </div>

  <hr class="divider" />
  <a href="/" class="chat-link">&#x1F4AC; Continue as guest</a>
</div>

<script>
  function switchTab(tab) {{
    document.getElementById('panel-login').style.display = tab === 'login' ? 'block' : 'none';
    document.getElementById('panel-register').style.display = tab === 'register' ? 'block' : 'none';
    document.getElementById('tab-login').className = 'tab' + (tab === 'login' ? ' active' : '');
    document.getElementById('tab-register').className = 'tab' + (tab === 'register' ? ' active' : '');
  }}
</script>
</body>
</html>"""


def _user_dashboard_page(user, reservations: list, notifications: list) -> str:
    unread = sum(1 for n in notifications if not n.is_read)

    # Build reservations table
    if not reservations:
        res_html = '<p style="color:#a0aec0;padding:24px 0;text-align:center;">No reservations yet. <a href="/" style="color:#0f3460;">Start a chat</a> to book a space.</p>'
    else:
        rows = []
        for r in reservations:
            short_id = _esc(r.reservation_id[:8].upper())
            status_colors = {"approved": "#27ae60", "pending": "#f39c12", "rejected": "#e74c3c"}
            sc = status_colors.get(r.status, "#718096")
            rows.append(f"""
            <tr>
              <td><span class="res-id">{short_id}</span></td>
              <td>{_esc(r.car_number)}</td>
              <td>{_esc(r.start_datetime)}</td>
              <td>{_esc(r.end_datetime)}</td>
              <td><span class="space-badge space-{_esc(r.space_type)}">{_esc(r.space_type.replace('_',' ').title())}</span></td>
              <td><span style="color:{sc};font-weight:600;font-size:12px;">{_esc(r.status.upper())}</span></td>
              <td style="font-size:12px;color:#718096;">{(r.submitted_at or '')[:16].replace('T', ' ') or '—'}</td>
              <td style="font-size:12px;color:#718096;">{(getattr(r, 'reviewed_at', None) or '')[:16].replace('T', ' ') or '—'}</td>
            </tr>""")
        res_html = f"""<table>
          <thead><tr>
            <th>ID</th><th>Car</th><th>Start</th><th>End</th><th>Type</th><th>Status</th><th>Submitted</th><th>Reviewed</th>
          </tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

    # Build notifications list
    if not notifications:
        notif_html = '<p style="color:#a0aec0;padding:16px 0;text-align:center;">No notifications yet.</p>'
    else:
        items = []
        for n in notifications:
            approved = n.notification_type == "approved"
            bg = "#f0fff4" if approved else "#fff5f5"
            border_color = "#27ae60" if approved else "#e74c3c"
            icon = "&#x2705;" if approved else "&#x274C;"
            title = "Reservation Approved" if approved else "Reservation Not Approved"
            status_text = "Your parking request has been approved." if approved else "Your parking request was not approved."
            read_style = "opacity:0.7;" if n.is_read else ""
            import re as _re
            rid_match = _re.search(r"[A-F0-9]{8}", n.message or "")
            rid_str = f" (ID: {rid_match.group()})" if rid_match else ""
            reason_match = _re.search(r"Reason: (.+)", n.message or "")
            reason_html = f'<div style="font-size:12px;color:#4a5568;margin-top:2px;">Reason: {_esc(reason_match.group(1))}</div>' if reason_match else ""
            from datetime import datetime as _dt
            try:
                ts = _dt.fromisoformat(n.created_at).strftime("%d %b %Y at %H:%M") if n.created_at else ""
            except Exception:
                ts = (n.created_at or "")[:16].replace("T", " ")
            items.append(f"""
            <div style="background:{bg};border-left:4px solid {border_color};border-radius:8px;padding:12px 16px;margin-bottom:10px;{read_style}">
              <div style="font-weight:600;font-size:14px;">{icon} {title}{_esc(rid_str)}</div>
              <div style="font-size:13px;color:#2d3748;margin-top:3px;">{status_text}</div>
              {reason_html}
              <div style="font-size:11px;color:#718096;margin-top:6px;">&#x1F552; {_esc(ts)}</div>
            </div>""")
        notif_html = "".join(items)

    first_name_esc = _esc(user.first_name)
    last_name_esc = _esc(user.last_name)
    email_esc = _esc(user.email)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CityPark &mdash; My Dashboard</title>
  <style>
    {_BASE_STYLE}
    .page-body {{ padding: 32px 28px; max-width: 1100px; margin: 0 auto; }}
    h2 {{ font-size: 20px; color: #1a1a2e; margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 24px; }}
    @media(max-width:768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    .panel {{ background: white; border-radius: 14px; padding: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.07); }}
    .panel-title {{ font-size: 15px; font-weight: 700; color: #1a1a2e; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
    .badge-count {{ background: #e74c3c; color: white; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    thead th {{ text-align: left; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #718096; text-transform: uppercase; border-bottom: 1px solid #e2e8f0; }}
    tbody td {{ padding: 12px 12px; border-bottom: 1px solid #f0f2f5; }}
    tbody tr:last-child td {{ border-bottom: none; }}
    .res-id {{ font-family: monospace; font-size: 11px; background: #edf2f7; padding: 2px 6px; border-radius: 4px; }}
    .space-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
    .space-regular {{ background: #ebf8ff; color: #2b6cb0; }}
    .space-ev_charging {{ background: #f0fff4; color: #276749; }}
    .space-vip {{ background: #faf5ff; color: #6b46c1; }}
    .space-handicapped {{ background: #fffaf0; color: #c05621; }}
    .profile-row {{ display: flex; gap: 10px; margin-bottom: 10px; font-size: 13px; }}
    .profile-label {{ color: #718096; font-weight: 600; min-width: 80px; }}
    .btn-chat {{ display: inline-block; margin-top: 16px; background: #0f3460; color: white; padding: 10px 22px; border-radius: 8px; text-decoration: none; font-size: 13px; font-weight: 600; transition: background 0.2s; }}
    .btn-chat:hover {{ background: #e94560; }}
  </style>
</head>
<body>
<header>
  <div class="logo">P</div>
  <div class="header-text">
    <h1>CityPark Premium Parking</h1>
    <p>My Dashboard</p>
  </div>
  <div class="header-actions">
    <a href="/" class="nav-link">&#x1F4AC; Chat</a>
    <span style="color:rgba(255,255,255,0.75);font-size:13px;">Hi, {first_name_esc}</span>
    <form method="POST" action="/auth/logout" style="margin:0">
      <button type="submit" style="background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.25);color:white;padding:6px 14px;border-radius:20px;cursor:pointer;font-size:13px;">Logout</button>
    </form>
  </div>
</header>

<div class="page-body">
  <h2>&#x1F44B; Welcome back, {first_name_esc}!</h2>
  <div class="grid">
    <!-- Reservations panel -->
    <div>
      <div class="panel">
        <div class="panel-title">&#x1F4CB; My Reservations</div>
        {res_html}
        <a href="/" class="btn-chat">+ New Reservation</a>
      </div>
    </div>

    <!-- Right column: profile + notifications -->
    <div>
      <div class="panel" style="margin-bottom:20px;">
        <div class="panel-title">&#x1F464; My Profile</div>
        <div class="profile-row"><span class="profile-label">Name</span><span>{first_name_esc} {last_name_esc}</span></div>
        <div class="profile-row"><span class="profile-label">Email</span><span>{email_esc}</span></div>
        <div class="profile-row"><span class="profile-label">Car</span><span>{_esc(user.car_number or 'Not set')}</span></div>
      </div>

      <div class="panel">
        <div class="panel-title">
          &#x1F514; Notifications
          {"" if unread == 0 else f'<span class="badge-count">{unread} new</span>'}
        </div>
        {notif_html}
      </div>
    </div>
  </div>
</div>
</body>
</html>"""


def _chat_page(user=None) -> str:
    # Build conditional header actions
    if user:
        first_esc = _esc(user.first_name)
        header_actions = f"""
    <button class="btn-new" onclick="newSession()">&#43; New Chat</button>
    <div class="bell-wrapper" id="bell-wrapper">
      <button class="btn-bell" id="bell-btn" onclick="toggleNotifications()" title="Notifications">
        &#x1F514;<span class="bell-badge" id="bell-badge" style="display:none">0</span>
      </button>
      <div class="notif-panel" id="notif-panel" style="display:none"></div>
    </div>
    <a href="/dashboard" class="nav-link-inline">&#x1F4CA; My Dashboard</a>
    <form method="POST" action="/auth/logout" style="margin:0">
      <button type="submit" class="btn-logout">Logout</button>
    </form>"""
        notification_js = """
    loadNotifications();
    setInterval(loadNotifications, 30000);"""
        guest_banner = ""
        sidebar_html = ""
        sidebar_class = ""
    else:
        header_actions = """
    <button class="btn-new" onclick="newSession()">&#43; New Chat</button>
    <a href="/login" class="nav-link-inline">Login / Register</a>"""
        notification_js = ""
        guest_banner = """
  <div class="guest-banner" id="guest-banner">
    &#x1F511; <strong>Save your chats and track reservations</strong> &mdash;
    <a href="/login">Create a free account</a> or <a href="/login">log in</a>
  </div>"""
        sidebar_html = ""
        sidebar_class = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CityPark Parking Assistant</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; height: 100vh; display: flex; flex-direction: column; }}
    header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
      color: white; padding: 14px 24px; display: flex; align-items: center; gap: 14px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3); flex-shrink: 0;
    }}
    .logo {{ width: 40px; height: 40px; background: #e94560; border-radius: 10px;
      display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; }}
    .header-text h1 {{ font-size: 17px; font-weight: 700; }}
    .header-text p {{ font-size: 11px; color: #a0aec0; margin-top: 2px; }}
    .header-actions {{ margin-left: auto; display: flex; gap: 8px; align-items: center; }}
    .btn-new {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.25);
      color: white; padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 12px; transition: background 0.2s; }}
    .btn-new:hover {{ background: rgba(255,255,255,0.2); }}
    .nav-link-inline {{ color: rgba(255,255,255,0.85); text-decoration: none; font-size: 12px;
      padding: 6px 12px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); transition: all 0.2s; }}
    .nav-link-inline:hover {{ background: rgba(255,255,255,0.1); color: white; }}
    .btn-logout {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2);
      color: rgba(255,255,255,0.75); padding: 6px 12px; border-radius: 20px; cursor: pointer; font-size: 12px; transition: all 0.2s; }}
    .btn-logout:hover {{ background: rgba(233,69,96,0.3); color: white; border-color: rgba(233,69,96,0.5); }}

    /* Bell */
    .bell-wrapper {{ position: relative; }}
    .btn-bell {{ background: none; border: none; color: white; font-size: 18px; cursor: pointer; position: relative; padding: 4px 6px; }}
    .bell-badge {{
      position: absolute; top: 0; right: 0; background: #e94560; color: white;
      font-size: 10px; font-weight: 700; width: 16px; height: 16px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center; line-height: 1;
    }}
    .notif-panel {{
      position: absolute; right: 0; top: 40px; width: 300px; background: white;
      border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.18); z-index: 100;
      max-height: 360px; overflow-y: auto;
    }}
    .notif-item {{ padding: 12px 16px; border-bottom: 1px solid #f0f2f5; font-size: 13px; border-left: 3px solid transparent; }}
    .notif-item:last-child {{ border-bottom: none; }}
    .notif-item.unread {{ background: #f7f8fc; }}
    .notif-item.approved {{ border-left-color: #27ae60; }}
    .notif-item.rejected {{ border-left-color: #e74c3c; }}
    .notif-title {{ font-weight: 600; margin-bottom: 3px; }}
    .notif-msg {{ color: #4a5568; font-size: 12px; line-height: 1.4; }}
    .notif-ts {{ font-size: 11px; color: #a0aec0; margin-top: 5px; }}
    .notif-header {{ font-weight: 700; padding: 12px 16px; font-size: 13px; color: #1a1a2e; border-bottom: 1px solid #e2e8f0; }}
    .notif-empty {{ padding: 20px; text-align: center; color: #a0aec0; font-size: 13px; }}

    /* Layout */
    .main-layout {{ display: flex; flex: 1; overflow: hidden; }}
    .chat-area {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
    #chat-container {{ flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }}
    .guest-banner {{
      background: linear-gradient(135deg, #ebf8ff, #e6fffa); border: 1px solid #bee3f8;
      border-radius: 10px; padding: 12px 16px; font-size: 13px; color: #2c5282;
      margin-bottom: 8px;
    }}
    .guest-banner a {{ color: #0f3460; font-weight: 600; }}
    .msg {{ max-width: 72%; display: flex; flex-direction: column; }}
    .msg.user {{ align-self: flex-end; align-items: flex-end; }}
    .msg.assistant {{ align-self: flex-start; align-items: flex-start; }}
    .msg-time {{ font-size: 10px; color: #a0aec0; margin-top: 3px; padding: 0 2px; }}
    .bubble {{ padding: 11px 16px; border-radius: 18px; font-size: 14px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }}
    .msg.user .bubble {{ background: #0f3460; color: white; border-bottom-right-radius: 4px; }}
    .msg.assistant .bubble {{ background: white; color: #2d3748; border-bottom-left-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    .msg-label {{ font-size: 11px; color: #718096; margin-bottom: 4px; }}
    .typing {{ display: none; align-self: flex-start; }}
    .typing .bubble {{ background: white; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    .dots span {{ display: inline-block; width: 7px; height: 7px; margin: 0 2px;
      background: #a0aec0; border-radius: 50%; animation: bounce 1.2s infinite; }}
    .dots span:nth-child(2) {{ animation-delay: 0.2s; }}
    .dots span:nth-child(3) {{ animation-delay: 0.4s; }}
    @keyframes bounce {{ 0%,60%,100%{{transform:translateY(0)}} 30%{{transform:translateY(-6px)}} }}
    footer {{ background: white; padding: 14px 20px; border-top: 1px solid #e2e8f0; display: flex; gap: 10px; align-items: center; flex-shrink: 0; }}
    #msg-input {{ flex: 1; padding: 11px 16px; border: 1.5px solid #e2e8f0; border-radius: 24px; font-size: 14px; outline: none; transition: border-color 0.2s; }}
    #msg-input:focus {{ border-color: #0f3460; }}
    #send-btn {{ background: #0f3460; color: white; border: none; border-radius: 50%;
      width: 44px; height: 44px; cursor: pointer; font-size: 18px; transition: background 0.2s;
      display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
    #send-btn:hover {{ background: #e94560; }}
    #send-btn:disabled {{ background: #a0aec0; cursor: not-allowed; }}
  </style>
</head>
<body>
<header>
  <div class="logo">P</div>
  <div class="header-text">
    <h1>CityPark Parking Assistant</h1>
    <p>Your intelligent parking companion &bull; Available 24/7</p>
  </div>
  <div class="header-actions">
    {header_actions}
  </div>
</header>

<div class="main-layout">
  {sidebar_html}
  <div class="chat-area">
    <div id="chat-container">
      {guest_banner}
      <div class="msg assistant">
        <div class="msg-label">CityPark Assistant</div>
        <div class="bubble">Welcome to CityPark Premium Parking! &#x1F17F;&#xFE0F;

I can help you with:
&bull; Parking information (location, hours, prices, availability)
&bull; Making a parking space reservation
&bull; FAQs and general enquiries

How can I assist you today?</div>
      </div>
      <div class="typing" id="typing-indicator">
        <div class="bubble"><div class="dots"><span></span><span></span><span></span></div></div>
      </div>
    </div>
    <footer>
      <input id="msg-input" type="text" placeholder="Ask about parking or make a reservation..." autocomplete="off" />
      <button id="send-btn" onclick="sendMessage()" title="Send">&#10148;</button>
    </footer>
  </div>
</div>

<script>
  let threadId = localStorage.getItem('citypark_thread_id') || crypto.randomUUID();
  localStorage.setItem('citypark_thread_id', threadId);

  const chat = document.getElementById('chat-container');
  const input = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const typing = document.getElementById('typing-indicator');

  input.addEventListener('keydown', e => {{ if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendMessage(); }} }});

  function fmtTime(ts) {{
    try {{
      const d = ts ? new Date(ts) : new Date();
      return d.toLocaleString('en-GB', {{ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }});
    }} catch(e) {{ return ''; }}
  }}

  function addMessage(role, text, timestamp) {{
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    const label = document.createElement('div');
    label.className = 'msg-label';
    label.textContent = role === 'user' ? 'You' : 'CityPark Assistant';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    const timeEl = document.createElement('div');
    timeEl.className = 'msg-time';
    timeEl.textContent = fmtTime(timestamp);
    div.appendChild(label);
    div.appendChild(bubble);
    div.appendChild(timeEl);
    chat.insertBefore(div, typing);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }}

  async function sendMessage() {{
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    sendBtn.disabled = true;
    addMessage('user', text, new Date().toISOString());
    typing.style.display = 'flex';
    chat.scrollTop = chat.scrollHeight;
    try {{
      const res = await fetch('/chat', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ message: text, thread_id: threadId }})
      }});
      const data = await res.json();
      addMessage('assistant', data.response || 'Sorry, something went wrong.', new Date().toISOString());
      // Guest: suggest login after reservation approval submitted
      if (data.response && data.response.includes('awaiting administrator approval')) {{
        const bell = document.getElementById('bell-btn');
        if (!bell) {{
          addMessage('assistant', 'Want to track your approval status and get notified when it\\'s reviewed?\\n\\n👉 Create a free account at /login — takes 30 seconds.');
        }}
      }}
    }} catch (err) {{
      addMessage('assistant', 'Connection error. Please ensure the server is running.');
    }} finally {{
      typing.style.display = 'none';
      sendBtn.disabled = false;
      input.focus();
    }}
  }}

  function newSession() {{
    threadId = crypto.randomUUID();
    localStorage.setItem('citypark_thread_id', threadId);
    const msgs = chat.querySelectorAll('.msg');
    msgs.forEach(m => m.remove());
    const banner = document.getElementById('guest-banner');
    addMessage('assistant', 'New session started! How can I help you with parking today?');
    if (banner) chat.insertBefore(banner, chat.firstChild);
  }}

  // ── Notification system (logged-in only) ──
  async function loadNotifications() {{
    try {{
      const res = await fetch('/api/notifications');
      if (!res.ok) return;
      const data = await res.json();
      const badge = document.getElementById('bell-badge');
      if (!badge) return;
      if (data.unread_count > 0) {{
        badge.textContent = data.unread_count;
        badge.style.display = 'flex';
      }} else {{
        badge.style.display = 'none';
      }}
      window._notifications = data.notifications;
    }} catch (e) {{}}
  }}

  function toggleNotifications() {{
    const panel = document.getElementById('notif-panel');
    if (!panel) return;
    if (panel.style.display !== 'none') {{
      panel.style.display = 'none';
      return;
    }}
    renderNotifications();
    panel.style.display = 'block';
    fetch('/api/notifications/read', {{ method: 'POST' }});
    const badge = document.getElementById('bell-badge');
    if (badge) badge.style.display = 'none';
  }}

  function fmtNotifTime(ts) {{
    try {{
      const d = new Date(ts);
      return d.toLocaleString('en-GB', {{ day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }});
    }} catch(e) {{ return ts ? ts.substring(0, 16).replace('T', ' ') : ''; }}
  }}

  function renderNotifications() {{
    const panel = document.getElementById('notif-panel');
    if (!panel) return;
    const notes = window._notifications || [];
    if (notes.length === 0) {{
      panel.innerHTML = '<div class="notif-header">&#x1F514; Notifications</div><div class="notif-empty">No notifications yet.</div>';
      return;
    }}
    const items = notes.map(n => {{
      const approved = n.notification_type === 'approved';
      const icon = approved ? '&#x2705;' : '&#x274C;';
      const title = approved ? 'Reservation Approved' : 'Reservation Not Approved';
      const statusText = approved
        ? 'Your parking request has been approved.'
        : 'Your parking request was not approved.';
      const ridMatch = n.message.match(/[A-F0-9]{{8}}/);
      const rid = ridMatch ? ` (ID: ${{ridMatch[0]}})` : '';
      const reasonMatch = n.message.match(/Reason: (.+)/);
      const reason = reasonMatch ? `<div class="notif-msg" style="margin-top:2px;">Reason: ${{reasonMatch[1]}}</div>` : '';
      const readCls = n.is_read ? '' : ' unread';
      const typeCls = approved ? ' approved' : ' rejected';
      return `<div class="notif-item${{readCls}}${{typeCls}}">
        <div class="notif-title">${{icon}} ${{title}}${{rid}}</div>
        <div class="notif-msg">${{statusText}}</div>
        ${{reason}}
        <div class="notif-ts">&#x1F552; ${{fmtNotifTime(n.created_at)}}</div>
      </div>`;
    }}).join('');
    panel.innerHTML = '<div class="notif-header">&#x1F514; Notifications</div>' + items;
  }}

  // Close notification panel on outside click
  document.addEventListener('click', function(e) {{
    const wrapper = document.getElementById('bell-wrapper');
    if (wrapper && !wrapper.contains(e.target)) {{
      const panel = document.getElementById('notif-panel');
      if (panel) panel.style.display = 'none';
    }}
  }});

  // Init on page load
  {notification_js}
</script>
</body>
</html>"""


def start_server_thread() -> threading.Thread:
    config = uvicorn.Config(app, host="0.0.0.0", port=APPROVAL_SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    print(f"[ApprovalServer] Running at http://localhost:{APPROVAL_SERVER_PORT}")
    print(f"[ApprovalServer] Admin portal at http://localhost:{APPROVAL_SERVER_PORT}/admin")
    print(f"[ApprovalServer] User login at http://localhost:{APPROVAL_SERVER_PORT}/login")
    return thread
