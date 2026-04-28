import asyncio
import time
from logging import Logger

import httpx

from app.models.service import CheckResult, Service, ServiceStatus, utc_now
from app.services.alert import AlertManager
from app.services.storage import ServiceStore


class MonitoringEngine:
    def __init__(
        self,
        store: ServiceStore,
        alert_manager: AlertManager,
        logger: Logger,
        interval_seconds: int,
        timeout_seconds: float,
    ):
        self.store = store
        self.alert_manager = alert_manager
        self.logger = logger
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="sentinel-monitor")
        self.logger.info("Monitoring engine started")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self.logger.info("Monitoring engine stopped")

    async def run_once(self) -> list[CheckResult]:
        services = [service for service in await self.store.list_services() if service.enabled]
        if not services:
            return []

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_seconds,
        ) as client:
            return await asyncio.gather(
                *(self.check_service(client, service) for service in services)
            )

    async def check_service(
        self,
        client: httpx.AsyncClient,
        service: Service,
    ) -> CheckResult:
        previous_status = service.status
        started_at = time.perf_counter()
        checked_at = utc_now()

        try:
            response = await client.get(str(service.url))
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            response.raise_for_status()
            result = CheckResult(
                service_id=service.id,
                status=ServiceStatus.up,
                response_time_ms=elapsed_ms,
                checked_at=checked_at,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            result = CheckResult(
                service_id=service.id,
                status=ServiceStatus.down,
                response_time_ms=elapsed_ms,
                error=str(exc),
                checked_at=checked_at,
            )

        updated = service.model_copy(
            update={
                "status": result.status,
                "last_checked_at": result.checked_at,
                "last_response_time_ms": result.response_time_ms,
                "last_error": result.error,
                "uptime_checks": service.uptime_checks + 1,
                "failed_checks": service.failed_checks
                + (1 if result.status == ServiceStatus.down else 0),
            }
        )
        saved = await self.store.save_service(updated)
        await self.store.record_check(result)

        self.logger.info(
            "Checked service_id=%s name=%s status=%s response_time_ms=%s",
            saved.id,
            saved.name,
            saved.status,
            saved.last_response_time_ms,
        )

        if result.status == ServiceStatus.down:
            await self.alert_manager.notify_failure(saved)
        elif previous_status == ServiceStatus.down:
            await self.alert_manager.notify_recovery(saved)

        return result

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Monitoring cycle failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                continue
