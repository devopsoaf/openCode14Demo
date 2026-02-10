from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Alert(BaseModel):
    """Alert model"""

    service: str = Field(..., description="Service name that generated the alert")
    severity: SeverityLevel = Field(..., description="Alert severity level")
    message: str = Field(..., description="Alert message")
    category: Optional[str] = Field(None, description="Alert category (CPU, Memory, Disk, Network, etc.)")
    labels: Optional[Dict[str, str]] = Field(default_factory=dict, description="Additional labels")
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Alert timestamp",
    )


class AlertResponse(BaseModel):
    """Alert response model"""

    alert_id: str
    incident_id: Optional[str] = None
    status: str
    action: str
    timestamp: datetime


class HealthCheck(BaseModel):
    """Health check response model"""

    status: str
    timestamp: datetime
    service: str
    version: str
    uptime: float
    checks: Dict[str, str]
