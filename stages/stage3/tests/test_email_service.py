from unittest.mock import patch, MagicMock


def test_console_fallback_when_no_credentials(capsys):
    from src.admin.email_service import send_approval_email
    with patch("src.admin.email_service.ADMIN_EMAIL", ""), \
         patch("src.admin.email_service.SENDER_EMAIL", ""), \
         patch("src.admin.email_service.SENDER_APP_PASSWORD", ""):
        result = send_approval_email("test-rid-s2-001", {
            "name": "John", "surname": "Doe", "car_number": "ABC-123",
            "start_datetime": "2026-06-10 09:00", "end_datetime": "2026-06-10 18:00",
            "space_type": "regular",
        })
    assert result is False
    assert "ADMIN ACTION REQUIRED" in capsys.readouterr().out


def test_email_falls_back_on_smtp_error(capsys):
    from src.admin.email_service import send_approval_email
    with patch("src.admin.email_service.ADMIN_EMAIL", "admin@test.com"), \
         patch("src.admin.email_service.SENDER_EMAIL", "sender@gmail.com"), \
         patch("src.admin.email_service.SENDER_APP_PASSWORD", "badpass"), \
         patch("smtplib.SMTP_SSL", side_effect=Exception("Connection refused")):
        result = send_approval_email("test-rid-s2-002", {
            "name": "Jane", "surname": "Smith", "car_number": "XYZ-999",
            "start_datetime": "2026-06-11 10:00", "end_datetime": "2026-06-11 16:00",
            "space_type": "vip",
        })
    assert result is False
    assert "ADMIN ACTION REQUIRED" in capsys.readouterr().out


def test_email_sends_with_valid_credentials():
    from src.admin.email_service import send_approval_email
    with patch("src.admin.email_service.ADMIN_EMAIL", "admin@test.com"), \
         patch("src.admin.email_service.SENDER_EMAIL", "sender@gmail.com"), \
         patch("src.admin.email_service.SENDER_APP_PASSWORD", "fakepassword"), \
         patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = send_approval_email("test-rid-s2-003", {
            "name": "Bob", "surname": "Jones", "car_number": "DEF-456",
            "start_datetime": "2026-06-12 09:00", "end_datetime": "2026-06-12 18:00",
            "space_type": "regular",
        })
    assert result is True
