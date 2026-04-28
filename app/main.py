from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes.api import dashboard_router, router
from app.services.alert import AlertManager
from app.services.logger import configure_logging
from app.services.monitor import MonitoringEngine
from app.services.storage import ServiceStore


def create_app(start_monitor: bool = True) -> FastAPI:
    settings = get_settings()
    logger = configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = ServiceStore(settings.database_file, seed_file=settings.data_file)
        alert_manager = AlertManager(
            logger,
            settings.alert_cooldown_seconds,
            webhook_url=str(settings.alert_webhook_url)
            if settings.alert_webhook_url
            else None,
        )
        monitor = MonitoringEngine(
            store=store,
            alert_manager=alert_manager,
            logger=logger,
            interval_seconds=settings.monitor_interval_seconds,
            timeout_seconds=settings.request_timeout_seconds,
        )

        app.state.service_store = store
        app.state.monitor = monitor
        if start_monitor:
            monitor.start()
        logger.info("%s started", settings.app_name)

        try:
            yield
        finally:
            await monitor.stop()
            logger.info("%s shutdown complete", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Monitor external services, record uptime, and emit alerts.",
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api")
    app.include_router(dashboard_router)
    return app


app = create_app()
