import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.config import ADMIN_EMAIL, SENDER_EMAIL, SENDER_APP_PASSWORD, APPROVAL_SERVER_URL, ADMIN_SECRET_TOKEN


def _build_html(reservation_id: str, data: dict) -> str:
    approve_url = f"{APPROVAL_SERVER_URL}/approve/{reservation_id}?token={ADMIN_SECRET_TOKEN}"
    reject_url = f"{APPROVAL_SERVER_URL}/reject/{reservation_id}?token={ADMIN_SECRET_TOKEN}"
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
      <h2 style="color:#2c3e50">CityPark — New Reservation Request</h2>
      <p>A new parking reservation requires your approval.</p>
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><b>Reservation ID</b></td>
            <td style="padding:8px;border:1px solid #ddd">{reservation_id}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><b>Name</b></td>
            <td style="padding:8px;border:1px solid #ddd">{data.get('name','')} {data.get('surname','')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><b>Car Number</b></td>
            <td style="padding:8px;border:1px solid #ddd">{data.get('car_number','')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><b>Start</b></td>
            <td style="padding:8px;border:1px solid #ddd">{data.get('start_datetime','')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><b>End</b></td>
            <td style="padding:8px;border:1px solid #ddd">{data.get('end_datetime','')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><b>Space Type</b></td>
            <td style="padding:8px;border:1px solid #ddd">{data.get('space_type','').replace('_',' ').title()}</td></tr>
      </table>
      <div style="margin-top:24px;text-align:center">
        <a href="{approve_url}" style="background:#27ae60;color:white;padding:12px 32px;text-decoration:none;border-radius:4px;margin-right:16px;font-size:16px">
          Approve
        </a>
        <a href="{reject_url}" style="background:#e74c3c;color:white;padding:12px 32px;text-decoration:none;border-radius:4px;font-size:16px">
          Reject
        </a>
      </div>
      <p style="color:#888;font-size:12px;margin-top:24px">
        CityPark Premium Parking &mdash; Automated Notification
      </p>
    </body></html>
    """


def send_approval_email(reservation_id: str, data: dict) -> bool:
    if not all([ADMIN_EMAIL, SENDER_EMAIL, SENDER_APP_PASSWORD]):
        _console_fallback(reservation_id, data)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[CityPark] Reservation Approval Required — {reservation_id[:8]}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = ADMIN_EMAIL
        msg.attach(MIMEText(_build_html(reservation_id, data), "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, ADMIN_EMAIL, msg.as_string())

        print(f"[Email] Approval request sent to {ADMIN_EMAIL} for reservation {reservation_id[:8]}")
        return True

    except Exception as e:
        print(f"[Email] Failed to send email: {e}. Falling back to console.")
        _console_fallback(reservation_id, data)
        return False


def _console_fallback(reservation_id: str, data: dict) -> None:
    approve_url = f"{APPROVAL_SERVER_URL}/approve/{reservation_id}?token={ADMIN_SECRET_TOKEN}"
    reject_url = f"{APPROVAL_SERVER_URL}/reject/{reservation_id}?token={ADMIN_SECRET_TOKEN}"
    print("\n" + "=" * 60)
    print("  ADMIN ACTION REQUIRED — New Reservation")
    print("=" * 60)
    print(f"  ID        : {reservation_id}")
    print(f"  Name      : {data.get('name','')} {data.get('surname','')}")
    print(f"  Car       : {data.get('car_number','')}")
    print(f"  Start     : {data.get('start_datetime','')}")
    print(f"  End       : {data.get('end_datetime','')}")
    print(f"  Space     : {data.get('space_type','')}")
    print("-" * 60)
    print(f"  APPROVE   : {approve_url}")
    print(f"  REJECT    : {reject_url}")
    print("=" * 60 + "\n")
