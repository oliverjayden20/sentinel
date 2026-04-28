from datetime import datetime, timedelta, timezone
from logging import Logger

import httpx

from app.models.service import Service


class AlertManager:
    def __init__(
        self,
        logger: Logger,
        cooldown_seconds: int,
        webhook_url: str | None = None,
    ):
        self.logger = logger
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.webhook_url = webhook_url
        self._last_alert_at: dict[str, datetime] = {}

    async def notify_failure(self, service: Service) -> None:
        now = datetime.now(timezone.utc)
        last_alert_at = self._last_alert_at.get(service.id)
        if last_alert_at and now - last_alert_at < self.cooldown:
            return

        self._last_alert_at[service.id] = now
        self.logger.warning(
            "ALERT service_id=%s name=%s url=%s error=%s",
            service.id,
            service.name,
            service.url,
            service.last_error or "unknown failure",
        )
        await self._send_webhook(
            {
                "event": "service_down",
                "service_id": service.id,
                "name": service.name,
                "url": str(service.url),
                "error": service.last_error,
                "occurred_at": now.isoformat(),
            }
        )

    async def notify_recovery(self, service: Service) -> None:
        if service.id in self._last_alert_at:
            self.logger.info(
                "RECOVERY service_id=%s name=%s url=%s",
                service.id,
                service.name,
                service.url,
            )
            self._last_alert_at.pop(service.id, None)
            await self._send_webhook(
                {
                    "event": "service_recovered",
                    "service_id": service.id,
                    "name": service.name,
                    "url": str(service.url),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    async def _send_webhook(self, payload: dict[str, object]) -> None:
        if not self.webhook_url:
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
        except Exception:
            self.logger.exception("Failed to deliver alert webhook")
