from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class IncidentCreate(BaseModel):
    """Request body for creating a new incident."""

    title: str = Field(..., max_length=500, description="Incident title")
    service: str = Field(..., description="Affected service name")
    severity: SeverityLevel = Field(..., description="Incident severity")
    description: Optional[str] = Field(None, description="Detailed description")


class IncidentUpdate(BaseModel):
    """Request body for updating an incident (PATCH)."""

    status: Optional[IncidentStatus] = Field(None, description="New status")
    assigned_to: Optional[str] = Field(None, description="Assignee engineer name")
    note: Optional[str] = Field(None, description="Note to append")
    author: Optional[str] = Field(None, description="Author of the note")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class IncidentResponse(BaseModel):
    """Full incident response with timeline data."""

    id: Optional[str] = None
    incident_id: str
    title: str
    description: Optional[str] = None
    service: str
    severity: SeverityLevel
    status: IncidentStatus
    assigned_to: Optional[str] = None
    notes: List = Field(default_factory=list)
    alerts: List[Dict] = Field(default_factory=list)
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IncidentMetrics(BaseModel):
    """MTTA / MTTR for a specific incident."""

    incident_id: str
    mtta_seconds: Optional[float] = None
    mttr_seconds: Optional[float] = None
    status: IncidentStatus


class IncidentAnalyticsResponse(BaseModel):
    """Historical incident analytics."""

    total_incidents: int = 0
    open_count: int = 0
    acknowledged_count: int = 0
    resolved_count: int = 0
    avg_mtta_seconds: Optional[float] = None
    avg_mttr_seconds: Optional[float] = None
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_service: Dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------------


class HealthCheck(BaseModel):
    """Health check response model"""

    status: str
    timestamp: datetime
    service: str
    version: str
    uptime: float
    checks: Dict[str, str]
