import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.database import get_db_connection
from app.http_client import get_http_client
from app.metrics import (
    incident_mtta_seconds,
    incident_mttr_seconds,
    incidents_total,
    notifications_sent_total,
    open_incidents,
)
from app.models import (
    IncidentAnalyticsResponse,
    IncidentCreate,
    IncidentMetrics,
    IncidentResponse,
    IncidentStatus,
    IncidentUpdate,
    SeverityLevel,
)
from app.ws import manager as ws_manager
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /incidents — create a new incident
# ---------------------------------------------------------------------------
@router.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(payload: IncidentCreate):
    """
    Create a new incident.
    1. Store in incidents.incidents
    2. Call On-Call Service to find assignee
    3. Call Notification Service to alert the on-call engineer
    """
    incident_id = f"inc-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # ── 1. Store incident ─────────────────────────────────────
    with get_db_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents.incidents
                    (incident_id, title, description, service, severity, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s::severity_level, 'open'::incident_status, %s, %s)
                RETURNING id, incident_id, title, description, service, severity,
                          status, assigned_to, notes, created_at, acknowledged_at,
                          resolved_at, updated_at
                """,
                (
                    incident_id,
                    payload.title,
                    payload.description,
                    payload.service,
                    payload.severity.value,
                    now,
                    now,
                ),
            )
            row = cur.fetchone()

    logger.info(f"Incident created: {incident_id}")

    # Increment metrics
    incidents_total.labels(status="open", severity=payload.severity.value).inc()
    open_incidents.labels(severity=payload.severity.value).inc()

    # ── 2. Call On-Call Service for assignment ─────────────────
    assigned_to: Optional[str] = None
    oncall_email: Optional[str] = None
    try:
        client = get_http_client()
        resp = await client.get(
            f"{settings.ONCALL_SERVICE_URL}/api/v1/oncall/current",
            params={"team": payload.service},
        )
        if resp.status_code == 200:
            data = resp.json()
            # Expect {"primary": {"name": ..., "email": ...}, ...}
            primary = data.get("primary")
            if primary:
                assigned_to = primary.get("name") or primary.get("email")
                oncall_email = primary.get("email")
    except Exception as e:
        logger.warning(f"On-Call service unavailable, skipping assignment: {e}")

    # Persist assignment if found
    if assigned_to:
        with get_db_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE incidents.incidents SET assigned_to = %s WHERE incident_id = %s",
                    (assigned_to, incident_id),
                )

    # ── 2b. Start escalation timer in On-Call Service ─────────
    if assigned_to:
        try:
            client = get_http_client()
            await client.post(
                f"{settings.ONCALL_SERVICE_URL}/api/v1/timers/start",
                json={
                    "incident_id": incident_id,
                    "team": payload.service,
                    "assigned_to": assigned_to,
                },
            )
            logger.info(f"Escalation timer started for {incident_id}")
        except Exception as e:
            logger.warning(f"Could not start escalation timer for {incident_id}: {e}")

    # ── 3. Call Notification Service (SMTP email to on-call) ──
    notify_target = oncall_email or assigned_to or "unassigned"
    try:
        client = get_http_client()
        await client.post(
            f"{settings.NOTIFICATION_SERVICE_URL}/api/v1/notify",
            json={
                "incident_id": incident_id,
                "engineer": notify_target,
                "channel": "email",
                "message": f"New incident: {payload.title}\nService: {payload.service}\nSeverity: {payload.severity.value}",
                "severity": payload.severity.value,
            },
        )
        notifications_sent_total.labels(channel="email", status="sent").inc()
    except Exception as e:
        logger.warning(f"Notification service unavailable: {e}")
        notifications_sent_total.labels(channel="email", status="failed").inc()

    # Build response from the DB row
    notes = row["notes"] if isinstance(row["notes"], list) else json.loads(row["notes"] or "[]")

    resp = IncidentResponse(
        id=str(row["id"]),
        incident_id=row["incident_id"],
        title=row["title"],
        description=row["description"],
        service=row["service"],
        severity=row["severity"],
        status=row["status"],
        assigned_to=assigned_to,
        notes=notes,
        created_at=row["created_at"],
        acknowledged_at=row["acknowledged_at"],
        resolved_at=row["resolved_at"],
        updated_at=row["updated_at"],
    )

    # Broadcast to WebSocket clients
    await ws_manager.broadcast(
        "incident_created",
        {
            "incident_id": incident_id,
            "title": payload.title,
            "service": payload.service,
            "severity": payload.severity.value,
            "status": "open",
        },
    )

    return resp


# ---------------------------------------------------------------------------
# GET /incidents — list with filters
# ---------------------------------------------------------------------------
@router.get("/incidents")
async def list_incidents(
    status_filter: Optional[IncidentStatus] = Query(None, alias="status"),
    severity: Optional[SeverityLevel] = None,
    service: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List incidents with optional filters, ordered by created_at DESC."""
    conditions = []
    params: list = []

    if status_filter:
        conditions.append("status = %s::incident_status")
        params.append(status_filter.value)
    if severity:
        conditions.append("severity = %s::severity_level")
        params.append(severity.value)
    if service:
        conditions.append("service = %s")
        params.append(service)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Total count for pagination
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM incidents.incidents {where}",
                params[:],
            )
            total = cur.fetchone()["cnt"]

            # Fetch page
            page_params = params + [limit, offset]
            cur.execute(
                f"""
                SELECT id, incident_id, title, description, service, severity,
                       status, assigned_to, notes, created_at, acknowledged_at,
                       resolved_at, updated_at
                FROM incidents.incidents
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                page_params,
            )
            rows = cur.fetchall()

    # Normalise notes from JSONB
    for r in rows:
        if r["notes"] and not isinstance(r["notes"], list):
            r["notes"] = json.loads(r["notes"])
        r["id"] = str(r["id"])
        if r["assigned_to"]:
            r["assigned_to"] = str(r["assigned_to"])

    return {"incidents": rows, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# GET /incidents/analytics — historical aggregates (bonus +1pt)
# ---------------------------------------------------------------------------
@router.get("/incidents/analytics", response_model=IncidentAnalyticsResponse)
async def get_analytics():
    """Historical incident analytics: counts, avg MTTA/MTTR, breakdowns."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Total + status counts
            cur.execute(
                """
                SELECT
                    COUNT(*)                                                    AS total,
                    COUNT(*) FILTER (WHERE status = 'open')                     AS open_count,
                    COUNT(*) FILTER (WHERE status = 'acknowledged')             AS ack_count,
                    COUNT(*) FILTER (WHERE status = 'resolved')                 AS resolved_count,
                    AVG(EXTRACT(EPOCH FROM (acknowledged_at - created_at)))
                        FILTER (WHERE acknowledged_at IS NOT NULL)              AS avg_mtta,
                    AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)))
                        FILTER (WHERE resolved_at IS NOT NULL)                  AS avg_mttr
                FROM incidents.incidents
                """
            )
            summary = cur.fetchone()

            # By severity
            cur.execute("SELECT severity::text, COUNT(*) AS cnt FROM incidents.incidents GROUP BY severity")
            sev_rows = cur.fetchall()

            # By service
            cur.execute("SELECT service, COUNT(*) AS cnt FROM incidents.incidents GROUP BY service")
            svc_rows = cur.fetchall()

    return IncidentAnalyticsResponse(
        total_incidents=summary["total"],
        open_count=summary["open_count"],
        acknowledged_count=summary["ack_count"],
        resolved_count=summary["resolved_count"],
        avg_mtta_seconds=round(summary["avg_mtta"], 2) if summary["avg_mtta"] else None,
        avg_mttr_seconds=round(summary["avg_mttr"], 2) if summary["avg_mttr"] else None,
        by_severity={r["severity"]: r["cnt"] for r in sev_rows},
        by_service={r["service"]: r["cnt"] for r in svc_rows},
    )


# ---------------------------------------------------------------------------
# GET /incidents/{incident_id} — single incident with linked alerts
# ---------------------------------------------------------------------------
@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str):
    """Get a single incident by its incident_id, including linked alerts."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, incident_id, title, description, service, severity,
                       status, assigned_to, notes, created_at, acknowledged_at,
                       resolved_at, updated_at
                FROM incidents.incidents
                WHERE incident_id = %s
                """,
                (incident_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    # Fetch linked alerts
    linked_alerts: list = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.alert_id, a.service, a.severity, a.message, a.timestamp
                    FROM alerts.alerts a
                    JOIN incidents.incident_alerts ia ON ia.alert_id = a.id
                    WHERE ia.incident_id = %s
                    ORDER BY a.timestamp DESC
                    """,
                    (row["id"],),
                )
                linked_alerts = cur.fetchall()
    except Exception as e:
        logger.warning(f"Could not fetch linked alerts for {incident_id}: {e}")

    notes = row["notes"] if isinstance(row["notes"], list) else json.loads(row["notes"] or "[]")

    return IncidentResponse(
        id=str(row["id"]),
        incident_id=row["incident_id"],
        title=row["title"],
        description=row["description"],
        service=row["service"],
        severity=row["severity"],
        status=row["status"],
        assigned_to=str(row["assigned_to"]) if row["assigned_to"] else None,
        notes=notes,
        alerts=linked_alerts,
        created_at=row["created_at"],
        acknowledged_at=row["acknowledged_at"],
        resolved_at=row["resolved_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# PATCH /incidents/{incident_id} — update status / assign / add notes
# ---------------------------------------------------------------------------
@router.patch("/incidents/{incident_id}", response_model=IncidentResponse)
async def update_incident(incident_id: str, payload: IncidentUpdate):
    """
    Update an incident:
    - status  → triggers MTTA/MTTR calculations
    - assigned_to → reassign
    - note    → append to JSONB notes array
    """
    # ── Fetch current incident ────────────────────────────────
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, incident_id, title, description, service, severity,
                       status, assigned_to, notes, created_at, acknowledged_at,
                       resolved_at, updated_at
                FROM incidents.incidents
                WHERE incident_id = %s
                """,
                (incident_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    now = datetime.now(timezone.utc)
    updates: list[str] = []
    params: list = []

    # ── Status transition ─────────────────────────────────────
    if payload.status:
        new_status = payload.status.value
        severity = row["severity"]

        updates.append("status = %s::incident_status")
        params.append(new_status)

        # Acknowledge → calculate MTTA
        if new_status == "acknowledged" and row["acknowledged_at"] is None:
            updates.append("acknowledged_at = %s")
            params.append(now)

            created_at = row["created_at"]
            mtta = (now - created_at).total_seconds()
            incident_mtta_seconds.labels(severity=severity).observe(mtta)
            logger.info(f"Incident {incident_id} acknowledged — MTTA {mtta:.1f}s")

        # Resolve → calculate MTTR
        if new_status == "resolved" and row["resolved_at"] is None:
            updates.append("resolved_at = %s")
            params.append(now)

            created_at = row["created_at"]
            mttr = (now - created_at).total_seconds()
            incident_mttr_seconds.labels(severity=severity).observe(mttr)
            logger.info(f"Incident {incident_id} resolved — MTTR {mttr:.1f}s")

            # Decrement open gauge
            open_incidents.labels(severity=severity).dec()

        # Update counter
        incidents_total.labels(status=new_status, severity=severity).inc()

        # Cancel escalation timer on acknowledge or resolve
        if new_status in ("acknowledged", "resolved", "closed", "mitigated"):
            try:
                client = get_http_client()
                await client.post(
                    f"{settings.ONCALL_SERVICE_URL}/api/v1/timers/cancel",
                    json={"incident_id": incident_id},
                )
                logger.info(f"Escalation timer cancelled for {incident_id}")
            except Exception as e:
                logger.warning(f"Could not cancel escalation timer for {incident_id}: {e}")

    # ── Assignment ────────────────────────────────────────────
    if payload.assigned_to is not None:
        updates.append("assigned_to = %s")
        params.append(payload.assigned_to)

    # ── Note append ───────────────────────────────────────────
    if payload.note:
        updates.append("notes = notes || %s::jsonb")
        note_obj = {
            "author": payload.author or "System",
            "content": payload.note,
            "created_at": now.isoformat(),
        }
        note_entry = json.dumps([note_obj])
        params.append(note_entry)

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    updates.append("updated_at = %s")
    params.append(now)
    params.append(incident_id)

    set_clause = ", ".join(updates)

    with get_db_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE incidents.incidents
                SET {set_clause}
                WHERE incident_id = %s
                RETURNING id, incident_id, title, description, service, severity,
                          status, assigned_to, notes, created_at, acknowledged_at,
                          resolved_at, updated_at
                """,
                params,
            )
            updated = cur.fetchone()

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found after update",
        )

    notes = updated["notes"] if isinstance(updated["notes"], list) else json.loads(updated["notes"] or "[]")

    resp = IncidentResponse(
        id=str(updated["id"]),
        incident_id=updated["incident_id"],
        title=updated["title"],
        description=updated["description"],
        service=updated["service"],
        severity=updated["severity"],
        status=updated["status"],
        assigned_to=str(updated["assigned_to"]) if updated["assigned_to"] else None,
        notes=notes,
        created_at=updated["created_at"],
        acknowledged_at=updated["acknowledged_at"],
        resolved_at=updated["resolved_at"],
        updated_at=updated["updated_at"],
    )

    # Broadcast to WebSocket clients
    await ws_manager.broadcast(
        "incident_updated",
        {
            "incident_id": updated["incident_id"],
            "status": updated["status"],
            "severity": updated["severity"],
            "service": updated["service"],
        },
    )

    return resp


# ---------------------------------------------------------------------------
# GET /incidents/{incident_id}/metrics — MTTA & MTTR for one incident
# ---------------------------------------------------------------------------
@router.get("/incidents/{incident_id}/metrics", response_model=IncidentMetrics)
async def get_incident_metrics(incident_id: str):
    """Return MTTA and MTTR in seconds for a specific incident."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT incident_id, status, created_at, acknowledged_at, resolved_at
                FROM incidents.incidents
                WHERE incident_id = %s
                """,
                (incident_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    mtta = None
    mttr = None

    if row["acknowledged_at"] and row["created_at"]:
        mtta = (row["acknowledged_at"] - row["created_at"]).total_seconds()

    if row["resolved_at"] and row["created_at"]:
        mttr = (row["resolved_at"] - row["created_at"]).total_seconds()

    return IncidentMetrics(
        incident_id=row["incident_id"],
        mtta_seconds=mtta,
        mttr_seconds=mttr,
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# DELETE /incidents/{incident_id} — delete an incident
# ---------------------------------------------------------------------------
@router.delete("/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_incident(incident_id: str):
    """Delete an incident and its linked alert associations."""
    with get_db_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            # Get DB id first
            cur.execute(
                "SELECT id FROM incidents.incidents WHERE incident_id = %s",
                (incident_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

            db_id = row["id"]
            # Remove join table entries
            cur.execute("DELETE FROM incidents.incident_alerts WHERE incident_id = %s", (db_id,))
            # Remove notification log entries
            cur.execute(
                "DELETE FROM incidents.notification_log WHERE incident_id = %s",
                (db_id,),
            )
            # Remove the incident
            cur.execute("DELETE FROM incidents.incidents WHERE id = %s", (db_id,))
