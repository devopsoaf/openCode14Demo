import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.database import get_db_connection
from app.http_client import get_http_client
from app.metrics import alerts_correlated_total, alerts_received_total
from app.models import Alert, AlertResponse, SeverityLevel
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /alerts — receive, store, correlate
# ---------------------------------------------------------------------------
@router.post("/alerts", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(alert: Alert):
    """
    Receive and process an alert.
    1. Store in alerts.alerts
    2. Correlate against open incidents (same service+severity within window)
    3. If match → link to existing incident
    4. If no match → create new incident via Incident Management service
    """
    # Increment received metric
    alerts_received_total.labels(
        severity=alert.severity.value,
        service=alert.service,
    ).inc()

    alert_id = f"alert-{uuid.uuid4().hex[:12]}"
    # Merge category into labels so it's persisted and queryable
    merged_labels = dict(alert.labels or {})
    if alert.category:
        merged_labels["category"] = alert.category
    labels_json = json.dumps(merged_labels) if merged_labels else "{}"
    ts = alert.timestamp or datetime.now(timezone.utc)

    # ── 1. Store raw alert ────────────────────────────────────
    with get_db_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts.alerts
                    (alert_id, service, severity, message, labels, timestamp)
                VALUES (%s, %s, %s::severity_level, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (
                    alert_id,
                    alert.service,
                    alert.severity.value,
                    alert.message,
                    labels_json,
                    ts,
                ),
            )
            row = cur.fetchone()
            alert_db_id = row["id"]  # UUID PK for FK references

    logger.info(f"Alert stored: {alert_id} (db id {alert_db_id})")

    # ── 2. Correlation query ──────────────────────────────────
    incident_id: Optional[str] = None
    action = "new_incident"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT incident_id, id
                FROM incidents.incidents
                WHERE service   = %s
                  AND severity  = %s::severity_level
                  AND status    IN ('open', 'acknowledged')
                  AND created_at >= now() - interval '%s minutes'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    alert.service,
                    alert.severity.value,
                    settings.CORRELATION_WINDOW_MINUTES,
                ),
            )
            match = cur.fetchone()

    if match:
        # ── 2a. Link to existing incident ─────────────────────
        incident_id = match["incident_id"]
        incident_db_id = match["id"]
        action = "existing_incident"

        with get_db_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                # Link in join table
                cur.execute(
                    """
                    INSERT INTO incidents.incident_alerts (incident_id, alert_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (incident_db_id, alert_db_id),
                )
                # Update alert row with incident reference
                cur.execute(
                    "UPDATE alerts.alerts SET incident_id = %s WHERE id = %s",
                    (incident_db_id, alert_db_id),
                )

        logger.info(f"Alert {alert_id} correlated to existing incident {incident_id}")
    else:
        # ── 2b. Create new incident via Incident Management ───
        try:
            client = get_http_client()
            resp = await client.post(
                f"{settings.INCIDENT_SERVICE_URL}/api/v1/incidents",
                json={
                    "title": f"[{alert.severity.value.upper()}] {alert.service}: {alert.message[:120]}",
                    "service": alert.service,
                    "severity": alert.severity.value,
                    "description": alert.message,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            incident_id = data.get("incident_id")
            incident_db_id = data.get("id")  # UUID PK if returned

            # Link alert <-> incident
            if incident_db_id:
                with get_db_connection(autocommit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO incidents.incident_alerts (incident_id, alert_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (incident_db_id, alert_db_id),
                        )
                        cur.execute(
                            "UPDATE alerts.alerts SET incident_id = %s WHERE id = %s",
                            (incident_db_id, alert_db_id),
                        )

            logger.info(f"Alert {alert_id} → new incident {incident_id}")
        except Exception as e:
            # Graceful degradation: alert is stored, incident_id stays null
            logger.error(f"Failed to create incident for alert {alert_id}: {e}")
            incident_id = None
            action = "incident_creation_failed"

    # ── 3. Update correlation metric ──────────────────────────
    alerts_correlated_total.labels(result=action).inc()

    # Map internal metric label → user-facing action string
    action_map = {
        "existing_incident": "attached_to_existing_incident",
        "new_incident": "created_new_incident",
        "incident_creation_failed": "alert_stored_incident_creation_failed",
    }
    display_action = action_map.get(action, action)
    resp_status = "correlated" if incident_id else "created"

    # ── 4. Fire-and-forget AI analysis ────────────────────────
    try:
        if settings.AI_ANALYSIS_SERVICE_URL:
            client = get_http_client()
            await client.post(
                f"{settings.AI_ANALYSIS_SERVICE_URL}/api/v1/analyze",
                json={
                    "alert_id": alert_id,
                    "incident_id": incident_id if incident_id else None,
                    "message": alert.message,
                    "service": alert.service,
                    "severity": alert.severity.value,
                },
                timeout=5.0,
            )
            logger.info(f"AI analysis triggered for alert {alert_id}")
    except Exception as e:
        logger.warning(f"AI analysis call failed for {alert_id}: {e}")

    return AlertResponse(
        alert_id=alert_id,
        incident_id=incident_id,
        status=resp_status,
        action=display_action,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /alerts/{alert_id} — single alert
# ---------------------------------------------------------------------------
@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    """Get alert by ID from alerts.alerts"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT alert_id, service, severity, message, labels,
                       timestamp, incident_id, created_at
                FROM alerts.alerts
                WHERE alert_id = %s
                """,
                (alert_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    # Convert incident UUID → incident_id string if present
    inc_id = None
    if row["incident_id"]:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT incident_id FROM incidents.incidents WHERE id = %s",
                    (row["incident_id"],),
                )
                inc_row = cur.fetchone()
                if inc_row:
                    inc_id = inc_row["incident_id"]

    return {
        "alert_id": row["alert_id"],
        "service": row["service"],
        "severity": row["severity"],
        "message": row["message"],
        "labels": row["labels"],
        "timestamp": row["timestamp"],
        "incident_id": inc_id,
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# GET /alerts — list with filters
# ---------------------------------------------------------------------------
@router.get("/alerts")
async def list_alerts(
    service: Optional[str] = None,
    severity: Optional[SeverityLevel] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List alerts with optional filters, ordered by created_at DESC"""
    conditions = []
    params: list = []

    if service:
        conditions.append("service = %s")
        params.append(service)
    if severity:
        conditions.append("severity = %s::severity_level")
        params.append(severity.value)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Total count for pagination
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM alerts.alerts {where}",
                params[:],  # copy — don't mutate
            )
            total = cur.fetchone()["cnt"]

            # Fetch page
            page_params = params + [limit, offset]
            cur.execute(
                f"""
                SELECT alert_id, service, severity, message, labels,
                       timestamp, incident_id, created_at
                FROM alerts.alerts
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                page_params,
            )
            rows = cur.fetchall()

    return {
        "alerts": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# DELETE /alerts/{alert_id} — delete an alert
# ---------------------------------------------------------------------------
@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: str):
    """Delete an alert by its alert_id."""
    with get_db_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            # Remove from join table first (FK constraint)
            cur.execute(
                "DELETE FROM incidents.incident_alerts WHERE alert_id IN (SELECT id FROM alerts.alerts WHERE alert_id = %s)",
                (alert_id,),
            )
            cur.execute(
                "DELETE FROM alerts.alerts WHERE alert_id = %s RETURNING id",
                (alert_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
