import hmac
import threading
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from src.config import ADMIN_SECRET_TOKEN, APPROVAL_SERVER_PORT
from src.database.queries import (
    approve_reservation,
    get_pending_reservations,
    get_reservation,
    reject_reservation,
)

app = FastAPI(title="CityPark Stage 2 Admin Approval Server")


def _auth(token: str) -> None:
    if not hmac.compare_digest(token, ADMIN_SECRET_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid token")


@app.get("/health")
def health():
    return {"status": "ok", "stage": 2}


@app.get("/pending")
def pending_reservations(token: str = Query(...)):
    _auth(token)
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
        for r in get_pending_reservations()
    ]


@app.get("/approve/{reservation_id}", response_class=HTMLResponse)
def approve(reservation_id: str, token: str = Query(...)):
    _auth(token)
    record = get_reservation(reservation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if record.status != "pending":
        return f"<h1>Already processed</h1><p>{reservation_id} is {record.status}.</p>"
    approve_reservation(reservation_id)
    return f"<h1>Reservation approved</h1><p>{reservation_id}</p>"


@app.get("/reject/{reservation_id}", response_class=HTMLResponse)
def reject(reservation_id: str, token: str = Query(...), notes: str = Query(default="Rejected by administrator.")):
    _auth(token)
    record = get_reservation(reservation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if record.status != "pending":
        return f"<h1>Already processed</h1><p>{reservation_id} is {record.status}.</p>"
    reject_reservation(reservation_id, notes)
    return f"<h1>Reservation rejected</h1><p>{reservation_id}</p>"


def start_server_thread() -> threading.Thread:
    config = uvicorn.Config(app, host="127.0.0.1", port=APPROVAL_SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    print(f"[Stage2ApprovalServer] Running at http://127.0.0.1:{APPROVAL_SERVER_PORT}")
    return thread
