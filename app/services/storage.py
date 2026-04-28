import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.service import (
    CheckRecord,
    CheckResult,
    Service,
    ServiceCreate,
    ServiceStatus,
    ServiceUpdate,
    utc_now,
)


class ServiceNotFoundError(ValueError):
    pass


class ServiceStore:
    def __init__(self, database_file: Path, seed_file: Path | None = None):
        self.database_file = database_file
        self.seed_file = seed_file
        self._lock = asyncio.Lock()
        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    async def list_services(self) -> list[Service]:
        async with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM services ORDER BY created_at DESC"
                ).fetchall()
            return [self._row_to_service(row) for row in rows]

    async def get_service(self, service_id: str) -> Service:
        async with self._lock:
            service = self._get_service_unlocked(service_id)
            if service is None:
                raise ServiceNotFoundError(f"Service '{service_id}' was not found")
            return service

    async def create_service(self, payload: ServiceCreate) -> Service:
        async with self._lock:
            service = Service(**payload.model_dump())
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO services (
                        id, name, url, enabled, status, last_checked_at,
                        last_response_time_ms, last_error, uptime_checks,
                        failed_checks, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._service_values(service),
                )
            return service

    async def update_service(self, service_id: str, payload: ServiceUpdate) -> Service:
        async with self._lock:
            service = self._get_service_unlocked(service_id)
            if service is None:
                raise ServiceNotFoundError(f"Service '{service_id}' was not found")

            updated = service.model_copy(
                update={**payload.model_dump(exclude_unset=True), "updated_at": utc_now()}
            )
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE services
                    SET name = ?, url = ?, enabled = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        updated.name,
                        str(updated.url),
                        int(updated.enabled),
                        self._dump_datetime(updated.updated_at),
                        updated.id,
                    ),
                )
            return updated

    async def delete_service(self, service_id: str) -> None:
        async with self._lock:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
                if cursor.rowcount == 0:
                    raise ServiceNotFoundError(f"Service '{service_id}' was not found")

    async def save_service(self, updated_service: Service) -> Service:
        async with self._lock:
            existing = self._get_service_unlocked(updated_service.id)
            if existing is None:
                raise ServiceNotFoundError(
                    f"Service '{updated_service.id}' was not found"
                )

            saved = updated_service.model_copy(update={"updated_at": utc_now()})
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE services
                    SET status = ?, last_checked_at = ?, last_response_time_ms = ?,
                        last_error = ?, uptime_checks = ?, failed_checks = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        saved.status.value,
                        self._dump_datetime(saved.last_checked_at),
                        saved.last_response_time_ms,
                        saved.last_error,
                        saved.uptime_checks,
                        saved.failed_checks,
                        self._dump_datetime(saved.updated_at),
                        saved.id,
                    ),
                )
            return saved

    async def record_check(self, result: CheckResult) -> CheckRecord:
        async with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO service_checks (
                        service_id, status, response_time_ms, error, checked_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        result.service_id,
                        result.status.value,
                        result.response_time_ms,
                        result.error,
                        self._dump_datetime(result.checked_at),
                    ),
                )
                record_id = cursor.lastrowid

            return CheckRecord(
                id=record_id,
                service_id=result.service_id,
                status=result.status,
                response_time_ms=result.response_time_ms,
                error=result.error,
                checked_at=result.checked_at,
            )

    async def list_checks(
        self,
        service_id: str,
        limit: int = 50,
    ) -> list[CheckRecord]:
        async with self._lock:
            if self._get_service_unlocked(service_id) is None:
                raise ServiceNotFoundError(f"Service '{service_id}' was not found")

            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM service_checks
                    WHERE service_id = ?
                    ORDER BY checked_at DESC
                    LIMIT ?
                    """,
                    (service_id, limit),
                ).fetchall()
            return [self._row_to_check(row) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS services (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    last_checked_at TEXT,
                    last_response_time_ms REAL,
                    last_error TEXT,
                    uptime_checks INTEGER NOT NULL DEFAULT 0,
                    failed_checks INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_time_ms REAL,
                    error TEXT,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_service_checks_service_checked
                ON service_checks(service_id, checked_at DESC)
                """
            )

        self._seed_from_json_if_empty()

    def _seed_from_json_if_empty(self) -> None:
        if self.seed_file is None or not self.seed_file.exists():
            return

        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
            if count:
                return

            try:
                raw = json.loads(self.seed_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return

            for item in raw:
                service = Service.model_validate(item)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO services (
                        id, name, url, enabled, status, last_checked_at,
                        last_response_time_ms, last_error, uptime_checks,
                        failed_checks, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._service_values(service),
                )

    def _get_service_unlocked(self, service_id: str) -> Service | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM services WHERE id = ?",
                (service_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_service(row)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _service_values(self, service: Service) -> tuple[Any, ...]:
        return (
            service.id,
            service.name,
            str(service.url),
            int(service.enabled),
            service.status.value,
            self._dump_datetime(service.last_checked_at),
            service.last_response_time_ms,
            service.last_error,
            service.uptime_checks,
            service.failed_checks,
            self._dump_datetime(service.created_at),
            self._dump_datetime(service.updated_at),
        )

    def _row_to_service(self, row: sqlite3.Row) -> Service:
        return Service(
            id=row["id"],
            name=row["name"],
            url=row["url"],
            enabled=bool(row["enabled"]),
            status=ServiceStatus(row["status"]),
            last_checked_at=self._load_datetime(row["last_checked_at"]),
            last_response_time_ms=row["last_response_time_ms"],
            last_error=row["last_error"],
            uptime_checks=row["uptime_checks"],
            failed_checks=row["failed_checks"],
            created_at=self._load_datetime(row["created_at"]) or utc_now(),
            updated_at=self._load_datetime(row["updated_at"]) or utc_now(),
        )

    def _row_to_check(self, row: sqlite3.Row) -> CheckRecord:
        checked_at = self._load_datetime(row["checked_at"])
        if checked_at is None:
            checked_at = utc_now()
        return CheckRecord(
            id=row["id"],
            service_id=row["service_id"],
            status=ServiceStatus(row["status"]),
            response_time_ms=row["response_time_ms"],
            error=row["error"],
            checked_at=checked_at,
        )

    def _dump_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def _load_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)
