from calendar import monthrange
from datetime import datetime
import os
from zoneinfo import ZoneInfo

from app import EMAIL_CONFIG, send_daily_email, send_monthly_email


def run_scheduled_reports(today=None):
    if not EMAIL_CONFIG["enabled"]:
        raise RuntimeError("Email reports are disabled")
    if not EMAIL_CONFIG["smtp_user"] or not EMAIL_CONFIG["smtp_pass"]:
        raise RuntimeError("SMTP credentials are not configured")

    if today is None:
        timezone = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))
        today = datetime.now(timezone).date()
    send_daily_email(today)

    if today.day == monthrange(today.year, today.month)[1]:
        send_monthly_email(today.year, today.month)


def main():
    run_scheduled_reports()


if __name__ == "__main__":
    main()
