"""
Send daily scrape summary email after the full location scraper runs.
Uses Zoho ZeptoMail SMTP. Run as final step in scrape-full-locations workflow.
"""

import os
import smtplib
import ssl
import sys
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv

load_dotenv()


def _send_email_smtp(to_email: str, subject: str, html_body: str) -> bool:
    """Send email via Zoho ZeptoMail SMTP."""
    password = os.getenv("ZOHO_SMTP_PASSWORD")
    if not password:
        print("ZOHO_SMTP_PASSWORD not set")
        return False

    from_addr = os.getenv("ZOHO_FROM_EMAIL", "noreply@flightgrab.cc")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    server = os.getenv("ZOHO_SMTP_SERVER", "smtp.zeptomail.com")
    port = int(os.getenv("ZOHO_SMTP_PORT", "587"))
    username = os.getenv("ZOHO_SMTP_USER", "emailapikey")

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(server, port, context=context) as s:
                s.login(username, password)
                s.sendmail(from_addr, to_email, msg.as_string())
        else:
            with smtplib.SMTP(server, port) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(username, password)
                s.sendmail(from_addr, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def main():
    from db_manager import FlightDatabase

    to_email = (os.getenv("SCRAPE_SUMMARY_EMAIL") or "tparboosingh84@gmail.com").strip()

    db = FlightDatabase()
    db.connect()

    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM current_prices WHERE departure_date >= CURRENT_DATE")
    total_flights = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(DISTINCT origin || '-' || destination) FROM current_prices WHERE departure_date >= CURRENT_DATE"
    )
    total_routes = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM current_prices WHERE DATE(last_updated) = CURRENT_DATE"
    )
    updated_today = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(DISTINCT origin) FROM current_prices WHERE departure_date >= CURRENT_DATE"
    )
    distinct_origins = cursor.fetchone()[0]
    cursor.close()
    db.close()

    today = date.today().isoformat()
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #1a73e8 0%, #1557b0 100%); padding: 24px; text-align: center; color: white;">
            <h1 style="margin: 0;">✈️ Daily Scrape Summary</h1>
            <p style="margin: 8px 0 0;">{today}</p>
        </div>
        <div style="padding: 24px;">
            <h2>FlightGrab Database Status</h2>
            <div style="background: #f0f4ff; padding: 20px; border-radius: 12px; margin: 20px 0;">
                <p style="margin: 0 0 12px;"><strong>Total flight options</strong> (future dates)</p>
                <p style="font-size: 28px; font-weight: bold; color: #1a73e8; margin: 0;">{total_flights:,}</p>
                <p style="margin: 12px 0 0; color: #666;">{total_routes:,} routes · {distinct_origins} origins</p>
            </div>
            <p><strong>Updated today:</strong> {updated_today:,} flights</p>
        </div>
    </body>
    </html>
    """

    subject = f"✈️ FlightGrab: {total_flights:,} flights populated ({today})"
    if _send_email_smtp(to_email, subject, html):
        print(f"✓ Summary sent to {to_email}")
    else:
        print("✗ Failed to send summary email")
        sys.exit(1)


if __name__ == "__main__":
    main()
