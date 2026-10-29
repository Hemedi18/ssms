import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.core.config import settings
from app.core.logging import logger


def send_owner_escalation_alert(
    sender_phone: str,
    incoming_text: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    extra_notes: Optional[str] = None
) -> bool:
    """
    Sends an urgent email notification when a customer requests to communicate with the owner.
    Target: notifications@edusphere.co.tz (with forwarder/CC to hemedimdoe18@gmail.com).
    """
    to_email = settings.NOTIFICATION_EMAIL
    forward_email = settings.ALERT_FORWARD_EMAIL

    subject = f"🚨 URGENT OWNER CONTACT REQUEST: Customer {sender_phone} needs to speak with Owner!"

    # Format conversation history
    history_html = ""
    history_text = ""
    if conversation_history:
        for item in reversed(conversation_history):
            role = item.get("role", "User").upper()
            text = item.get("text", "")
            time_str = item.get("time", "")
            history_html += f"<li><strong>{role}</strong> ({time_str}): {text}</li>"
            history_text += f"- [{role}] {text}\n"
    else:
        history_html = "<li><em>No prior conversation history recorded.</em></li>"
        history_text = "No prior conversation history."

    # HTML Body
    html_content = f"""
    <html>
    <head>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f7fafc; padding: 20px; }}
        .card {{ background: #ffffff; border-radius: 10px; padding: 25px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.08); max-width: 650px; margin: auto; border-top: 5px solid #e53e3e; }}
        .header {{ font-size: 20px; font-weight: bold; color: #c53030; margin-bottom: 15px; }}
        .badge {{ background: #fed7d7; color: #9b2c2c; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 13px; display: inline-block; }}
        .section {{ margin-top: 20px; border-top: 1px solid #edf2f7; padding-top: 15px; }}
        .label {{ font-size: 13px; color: #718096; text-transform: uppercase; font-weight: bold; }}
        .phone {{ font-size: 24px; font-weight: bold; color: #2b6cb0; margin: 8px 0; }}
        .message-box {{ background: #edf2f7; border-left: 4px solid #3182ce; padding: 12px 15px; border-radius: 4px; font-size: 16px; margin-top: 8px; }}
        .history-list {{ background: #f7fafc; padding: 15px 20px; border-radius: 6px; font-size: 14px; color: #4a5568; }}
        .action-button {{ display: inline-block; background: #3182ce; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 20px; }}
        .footer {{ margin-top: 25px; font-size: 12px; color: #a0aec0; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">ACTION REQUIRED IMMEDIATELY</div>
        <div class="header">Customer Request to Speak with Owner</div>
        <p>A customer has explicitly requested to communicate with the owner or live management. AI auto-reply has been <strong>automatically paused</strong> for this contact.</p>

        <div class="section">
          <div class="label">Customer Phone Number</div>
          <div class="phone">{sender_phone}</div>
          <a href="tel:{sender_phone}" class="action-button">📞 Call Customer Now</a>
        </div>

        <div class="section">
          <div class="label">Triggering Incoming Message</div>
          <div class="message-box">"{incoming_text}"</div>
        </div>

        <div class="section">
          <div class="label">Recent Chat History</div>
          <ul class="history-list">
            {history_html}
          </ul>
        </div>

        <div class="footer">
          Delivered by SIM SMS Gateway &bull; Alert sent to {to_email} &bull; Forwarded to {forward_email}
        </div>
      </div>
    </body>
    </html>
    """

    # Plain text version for non-HTML email clients
    plain_content = f"""
    URGENT: Customer Request to Speak with Owner!
    ================================================
    Customer Phone: {sender_phone}
    Triggering Message: "{incoming_text}"

    AI auto-reply has been paused for this contact. Please contact this customer immediately!

    Recent Conversation History:
    {history_text}

    --
    SIM SMS Gateway System Alert
    Recipient: {to_email} | Forward: {forward_email}
    """

    recipients = [to_email]
    if forward_email and forward_email not in recipients:
        recipients.append(forward_email)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"SIM Gateway Alerts <{to_email}>"
    msg["To"] = to_email
    if forward_email:
        msg["Cc"] = forward_email

    msg.attach(MIMEText(plain_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    # Attempt SMTP transmission
    try:
        host = settings.SMTP_HOST or "localhost"
        port = settings.SMTP_PORT or 587
        logger.info(f"Connecting to SMTP {host}:{port} to send owner escalation alert for {sender_phone}")

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if settings.SMTP_USE_TLS:
                try:
                    server.starttls()
                except Exception:
                    pass

        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        server.sendmail(to_email, recipients, msg.as_string())
        server.quit()
        logger.info(f"Owner escalation alert sent successfully to {recipients} for {sender_phone}")
        return True
    except Exception as e:
        logger.warning(
            f"Direct SMTP alert failed ({e}). Logged urgent alert for owner: Phone={sender_phone}, "
            f"AlertEmail={to_email}, ForwardEmail={forward_email}"
        )
        return False
