"""
Check price alerts and send email notifications when prices drop.
Uses Zoho ZeptoMail SMTP. Run via cron or GitHub Actions.
Requires: ZOHO_SMTP_PASSWORD, DATABASE_URL
"""

import os
import smtplib
import ssl
import urllib.parse
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv

load_dotenv()


def build_booking_url(origin: str, destination: str, date: str, base_url: str = "") -> str:
    """Build app booking URL or fallback to Google Flights search."""
    if base_url and "book-redirect" in base_url:
        return base_url
    base = "https://www.google.com/travel/flights"
    q = f"One way flights from {origin} to {destination} on {date}"
    return f"{base}?q={urllib.parse.quote(q)}"


def send_alert_email(
    to_email: str,
    origin: str,
    destination: str,
    target_price: float,
    current_price: float,
    departure_date: str,
    booking_url: str,
    alert_id: int,
    manage_url: str = "",
) -> bool:
    """Send price alert email via Zoho ZeptoMail SMTP."""
    password = os.getenv("ZOHO_SMTP_PASSWORD")
    if not password:
        print("ZOHO_SMTP_PASSWORD not set (add ZeptoMail API key to .env)")
        return False

    pct = 0
    if target_price > 0:
        pct = int((target_price - current_price) / target_price * 100)

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #1a73e8 0%, #1557b0 100%); padding: 24px; text-align: center; color: white;">
            <h1 style="margin: 0;">✈️ Price Alert Triggered!</h1>
        </div>
        <div style="padding: 24px;">
            <h2>{origin} → {destination}</h2>
            <div style="background: #f0f4ff; padding: 20px; border-radius: 12px; margin: 20px 0;">
                <p style="margin: 0; color: #666;">Current price</p>
                <p style="font-size: 32px; font-weight: bold; color: #188038; margin: 8px 0;">${int(current_price)}</p>
                <p style="margin: 0; color: #666;">Your target: ${int(target_price)}</p>
                <p style="margin: 4px 0; color: #188038;">✓ {pct}% below target!</p>
            </div>
            <p><strong>Departure:</strong> {departure_date}</p>
            <div style="text-align: center; margin: 24px 0;">
                <a href="{booking_url}" style="background: #1a73e8; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold;">
                    Book Now →
                </a>
            </div>
            {f'<p style="color: #999; font-size: 12px; text-align: center;"><a href="{manage_url}">Manage alerts</a></p>' if manage_url else ''}
        </div>
    </body>
    </html>
    """

    from_addr = os.getenv("ZOHO_FROM_EMAIL", "noreply@flightgrab.cc")
    subject = f"✈️ Price Alert: {origin} → {destination} now ${int(current_price)}!"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

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
        print(f"✓ Alert sent to {to_email}: {origin}→{destination} ${current_price}")
        return True
    except Exception as e:
        print(f"✗ Failed to send to {to_email}: {e}")
        return False


def check_alerts():
    """Check all active alerts and send emails for triggered ones."""
    from db_manager import FlightDatabase

    db = FlightDatabase()
    db.connect()

    alerts = db.get_triggered_alerts()
    base_url = os.getenv("APP_URL", "https://flightgrab.com")
    manage_url = f"{base_url.rstrip('/')}/#alerts"

    sent = 0
    for a in alerts:
        booking_url = build_booking_url(
            a["origin"], a["destination"], a["departure_date"],
            a.get("booking_url", ""),
        )
        if send_alert_email(
            a["email"],
            a["origin"],
            a["destination"],
            a["target_price"],
            a["current_price"],
            a["departure_date"],
            booking_url,
            a["id"],
            manage_url,
        ):
            db.mark_alert_notified(a["id"])
            sent += 1

    print(f"✓ Processed {len(alerts)} triggered alerts, sent {sent} emails")
    db.close()


if __name__ == "__main__":
    check_alerts()
