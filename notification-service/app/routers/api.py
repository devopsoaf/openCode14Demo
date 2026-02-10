import logging
import smtplib
import time
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.database import get_db_connection
from app.metrics import notification_delivery_seconds, oncall_notifications_sent_total
from app.models import (
    NotificationChannel,
    NotificationListResponse,
    NotificationRequest,
    NotificationResponse,
    NotificationStatus,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-engineer email rate limiter (in-memory)
# ---------------------------------------------------------------------------
_email_last_sent: dict[str, float] = {}  # engineer_email → epoch timestamp


def _is_rate_limited(engineer: str) -> bool:
    """Return True if an email was already sent to this engineer within the cooldown window."""
    now = time.time()
    last = _email_last_sent.get(engineer)
    if last and (now - last) < settings.EMAIL_COOLDOWN_SECONDS:
        return True
    return False


def _record_email_sent(engineer: str) -> None:
    _email_last_sent[engineer] = time.time()


# ---------------------------------------------------------------------------
# Notification channel dispatchers
# ---------------------------------------------------------------------------


def _send_mock(notification_id: str, request: NotificationRequest) -> NotificationStatus:
    """Mock notification — log to stdout."""
    logger.info(
        f"[MOCK NOTIFICATION] id={notification_id} "
        f"incident={request.incident_id} "
        f"engineer={request.engineer} "
        f"message={request.message}"
    )
    return NotificationStatus.DELIVERED


async def _send_email(notification_id: str, request: NotificationRequest) -> NotificationStatus:
    """Send email via SendGrid (if API key set) or SMTP. Falls back to mock if neither configured."""
    # ── SendGrid path ──
    if getattr(settings, "SENDGRID_API_KEY", None):
        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_CLIENT_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": request.engineer}]}],
                        "from": {"email": settings.SENDGRID_FROM_EMAIL},
                        "subject": f"[ExpertMind Alert] {request.incident_id}",
                        "content": [{"type": "text/plain", "value": request.message}],
                    },
                )
            if resp.status_code in (200, 202):
                logger.info(f"[EMAIL SENT] id={notification_id} to={request.engineer} via SendGrid")
                return NotificationStatus.DELIVERED
            else:
                logger.error(f"[EMAIL ERROR] id={notification_id}: SendGrid {resp.status_code} {resp.text}")
                return NotificationStatus.FAILED
        except Exception as e:
            logger.error(f"[EMAIL ERROR] id={notification_id}: {e}")
            return NotificationStatus.FAILED

    # ── SMTP path ──
    smtp_password = getattr(settings, "SMTP_PASSWORD", "")
    if not smtp_password or not isinstance(smtp_password, str):
        logger.info(f"[EMAIL FALLBACK→MOCK] No SMTP_PASSWORD set. id={notification_id}")
        return _send_mock(notification_id, request)

    # ── Rate-limit: skip real email if this engineer was mailed recently ──
    if _is_rate_limited(request.engineer):
        logger.info(
            f"[EMAIL RATE-LIMITED] id={notification_id} to={request.engineer} "
            f"(cooldown {settings.EMAIL_COOLDOWN_SECONDS}s) — falling back to mock"
        )
        return _send_mock(notification_id, request)

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.SMTP_SENDER
        msg["To"] = request.engineer
        msg["Subject"] = f"[ExpertMind Alert] {request.incident_id}"

        sev = request.severity.value if request.severity else 'N/A'
        sev_upper = sev.upper()
        # Severity-based colors
        sev_colors = {
            'critical': ('#dc2626', '#fef2f2'),
            'high': ('#ea580c', '#fff7ed'),
            'medium': ('#ca8a04', '#fefce8'),
            'low': ('#2563eb', '#eff6ff'),
        }
        sev_color, sev_bg = sev_colors.get(sev, ('#6b7280', '#f9fafb'))

        # Parse message lines for better formatting
        message_lines = request.message.replace('\n', '<br>')

        # Plain-text body
        body_text = (
            f"Incident: {request.incident_id}\n"
            f"Severity: {sev}\n\n"
            f"{request.message}"
        )
        # HTML body — professional email template
        body_html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a;padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#1e293b;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.3);">
  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px 32px;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td><span style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">⚡ ExpertMind</span><br>
        <span style="font-size:12px;color:rgba(255,255,255,0.8);text-transform:uppercase;letter-spacing:1.5px;">Incident Alert</span>
      </td>
      <td align="right"><span style="background:{sev_color};color:#fff;padding:6px 16px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">{sev_upper}</span></td>
    </tr></table>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:32px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a;border-radius:8px;border:1px solid #334155;">
    <tr><td style="padding:20px;">
      <p style="margin:0 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#94a3b8;">Incident ID</p>
      <p style="margin:0 0 16px;font-size:15px;font-weight:600;color:#f1f5f9;font-family:monospace;">{request.incident_id}</p>
      <p style="margin:0 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#94a3b8;">Assigned To</p>
      <p style="margin:0 0 16px;font-size:14px;color:#e2e8f0;">{request.engineer}</p>
      <p style="margin:0 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#94a3b8;">Details</p>
      <p style="margin:0;font-size:14px;color:#cbd5e1;line-height:1.6;">{message_lines}</p>
    </td></tr></table>
    <!-- CTA -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
    <tr><td align="center">
      <a href="http://localhost:8080/incidents/{request.incident_id}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#ffffff;padding:12px 32px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;letter-spacing:0.3px;">View Incident →</a>
    </td></tr></table>
  </td></tr>
  <!-- Footer -->
  <tr><td style="padding:20px 32px;border-top:1px solid #334155;">
    <p style="margin:0;font-size:11px;color:#64748b;text-align:center;">ExpertMind Incident & On-Call Platform &middot; Automated alert — do not reply</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>
"""

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_SENDER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_SENDER, request.engineer, msg.as_string())

        logger.info(f"[EMAIL SENT] id={notification_id} to={request.engineer} via SMTP")
        _record_email_sent(request.engineer)
        return NotificationStatus.DELIVERED
    except Exception as e:
        logger.error(f"[EMAIL ERROR] id={notification_id}: {e}")
        return NotificationStatus.FAILED


async def _send_slack(notification_id: str, request: NotificationRequest) -> NotificationStatus:
    """Send notification to Slack via incoming webhook. Falls back to mock if no URL."""
    slack_url = settings.SLACK_WEBHOOK_URL
    if not slack_url:
        logger.info(f"[SLACK FALLBACK→MOCK] No SLACK_WEBHOOK_URL set. id={notification_id}")
        return _send_mock(notification_id, request)

    severity_emoji = {
        "critical": ":rotating_light:",
        "high": ":fire:",
        "medium": ":warning:",
        "low": ":information_source:",
    }
    emoji = severity_emoji.get(request.severity.value, ":bell:") if request.severity else ":bell:"

    payload = {
        "text": f"{emoji} *Incident {request.incident_id}*\nEngineer: {request.engineer}\n{request.message}",
        "username": "Incident Platform",
        "icon_emoji": ":rotating_light:",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_CLIENT_TIMEOUT) as client:
            resp = await client.post(slack_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"[SLACK SENT] id={notification_id}")
                return NotificationStatus.DELIVERED
            else:
                logger.error(f"[SLACK FAILED] id={notification_id} status={resp.status_code}")
                return NotificationStatus.FAILED
    except Exception as e:
        logger.error(f"[SLACK ERROR] id={notification_id}: {e}")
        return NotificationStatus.FAILED


async def _send_webhook(notification_id: str, request: NotificationRequest) -> NotificationStatus:
    """Send notification to webhook URL(s)."""
    urls = []
    if request.webhook_url:
        urls.append(request.webhook_url)
    urls.extend(settings.webhook_url_list)

    if not urls:
        logger.warning(f"[WEBHOOK] No webhook URLs configured. id={notification_id}")
        return NotificationStatus.FAILED

    payload = {
        "notification_id": notification_id,
        "incident_id": request.incident_id,
        "engineer": request.engineer,
        "severity": request.severity.value if request.severity else None,
        "message": request.message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    delivered = False
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_CLIENT_TIMEOUT) as client:
            for url in urls:
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code < 400:
                        logger.info(f"[WEBHOOK SENT] id={notification_id} url={url} status={resp.status_code}")
                        delivered = True
                    else:
                        logger.warning(f"[WEBHOOK FAILED] id={notification_id} url={url} status={resp.status_code}")
                except Exception as e:
                    logger.error(f"[WEBHOOK ERROR] id={notification_id} url={url}: {e}")
    except Exception as e:
        logger.error(f"[WEBHOOK CLIENT ERROR] id={notification_id}: {e}")

    return NotificationStatus.DELIVERED if delivered else NotificationStatus.FAILED


# ---------------------------------------------------------------------------
# POST /notify — send a notification
# ---------------------------------------------------------------------------
@router.post("/notify", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def send_notification(request: NotificationRequest):
    """
    Send a notification via the specified channel.
    1. Dispatch to channel handler (mock / email / webhook)
    2. Store notification record in DB
    3. Update Prometheus metrics
    """
    notification_id = f"notif-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # ── 1. Dispatch to channel ────────────────────────────────
    start = time.time()

    rate_limited = False
    duplicate_reason = None
    if request.channel == NotificationChannel.EMAIL:
        # Check if rate-limited before sending
        if _is_rate_limited(request.engineer):
            rate_limited = True
            duplicate_reason = (
                f"Duplicate notification for {request.engineer} within cooldown window "
                f"({settings.EMAIL_COOLDOWN_SECONDS}s) at {datetime.now(timezone.utc).isoformat()}"
            )
            logger.info(f"[DUPLICATE NOTIFICATION] {duplicate_reason}")
        delivery_status = await _send_email(notification_id, request)
    elif request.channel == NotificationChannel.WEBHOOK:
        delivery_status = await _send_webhook(notification_id, request)
    elif request.channel == NotificationChannel.SLACK:
        delivery_status = await _send_slack(notification_id, request)
    else:
        delivery_status = _send_mock(notification_id, request)

    duration = time.time() - start
    notification_delivery_seconds.labels(channel=request.channel.value).observe(duration)

    # ── 2. Store in DB ────────────────────────────────────────
    try:
        with get_db_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notifications.notifications
                        (notification_id, incident_id, engineer, channel,
                         status, message, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        notification_id,
                        request.incident_id,
                        request.engineer,
                        request.channel.value,
                        delivery_status.value,
                        request.message,
                        now,
                    ),
                )
                cur.fetchone()
    except Exception as e:
        logger.error(f"Failed to store notification {notification_id}: {e}")
        # Notification was still sent — don't fail the request

    # ── 3. Update metrics ─────────────────────────────────────
    oncall_notifications_sent_total.labels(
        channel=request.channel.value,
        status=delivery_status.value,
    ).inc()

    # Add rate_limited and duplicate_reason to response if applicable
    resp = NotificationResponse(
        notification_id=notification_id,
        incident_id=request.incident_id,
        engineer=request.engineer,
        channel=request.channel,
        status=delivery_status,
        message=request.message,
        timestamp=now,
    )
    # Attach extra fields for duplicate/rate-limited
    if rate_limited:
        resp_dict = resp.model_dump()
        resp_dict["rate_limited"] = True
        resp_dict["duplicate_reason"] = duplicate_reason
        return resp_dict
    return resp


# ---------------------------------------------------------------------------
# GET /notifications — list notification history
# ---------------------------------------------------------------------------
@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    incident_id: Optional[str] = None,
    channel: Optional[NotificationChannel] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List notification history with optional filters."""
    conditions = []
    params: list = []

    if incident_id:
        conditions.append("incident_id = %s")
        params.append(incident_id)
    if channel:
        conditions.append("channel = %s")
        params.append(channel.value)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Total count
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM notifications.notifications {where}",
                params[:],
            )
            total = cur.fetchone()["cnt"]

            # Fetch page
            page_params = params + [limit, offset]
            cur.execute(
                f"""
                SELECT notification_id, incident_id, engineer, channel,
                       status, message, created_at
                FROM notifications.notifications
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                page_params,
            )
            rows = cur.fetchall()

    return NotificationListResponse(
        notifications=rows,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /notifications/{notification_id} — single notification
# ---------------------------------------------------------------------------
@router.get("/notifications/{notification_id}")
async def get_notification(notification_id: str):
    """Get a single notification by its ID."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT notification_id, incident_id, engineer, channel,
                       status, message, created_at
                FROM notifications.notifications
                WHERE notification_id = %s
                """,
                (notification_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return row
