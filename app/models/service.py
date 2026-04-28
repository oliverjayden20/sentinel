from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ServiceStatus(str, Enum):
    unknown = "unknown"
    up = "up"
    down = "down"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    url: HttpUrl
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: HttpUrl | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class Service(ServiceBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: ServiceStatus = ServiceStatus.unknown
    last_checked_at: datetime | None = None
    last_response_time_ms: float | None = None
    last_error: str | None = None
    uptime_checks: int = 0
    failed_checks: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def calculate_uptime_percentage(self) -> float | None:
        if self.uptime_checks == 0:
            return None
        successful = self.uptime_checks - self.failed_checks
        return round((successful / self.uptime_checks) * 100, 2)

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["uptime_percentage"] = self.calculate_uptime_percentage()
        return data


class ServiceRead(Service):
    uptime_percentage: float | None = None


class CheckResult(BaseModel):
    service_id: str
    status: ServiceStatus
    response_time_ms: float | None = None
    error: str | None = None
    checked_at: datetime = Field(default_factory=utc_now)


class CheckRecord(BaseModel):
    id: int
    service_id: str
    status: ServiceStatus
    response_time_ms: float | None = None
    error: str | None = None
    checked_at: datetime
