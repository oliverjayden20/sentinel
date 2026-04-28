from typing import Annotated
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.models.service import (
    CheckRecord,
    CheckResult,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)
from app.services.monitor import MonitoringEngine
from app.services.storage import ServiceNotFoundError, ServiceStore
from app.utils.helpers import service_response, services_response


router = APIRouter()
dashboard_router = APIRouter()


def get_store(request: Request) -> ServiceStore:
    return request.app.state.service_store


def get_monitor(request: Request) -> MonitoringEngine:
    return request.app.state.monitor


StoreDep = Annotated[ServiceStore, Depends(get_store)]
MonitorDep = Annotated[MonitoringEngine, Depends(get_monitor)]


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/services", response_model=list[ServiceRead], tags=["services"])
async def list_services(store: StoreDep) -> list[ServiceRead]:
    services = await store.list_services()
    return services_response(services)


@router.post(
    "/services",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    tags=["services"],
)
async def create_service(payload: ServiceCreate, store: StoreDep) -> ServiceRead:
    service = await store.create_service(payload)
    return service_response(service)


@router.get("/services/{service_id}", response_model=ServiceRead, tags=["services"])
async def get_service(service_id: str, store: StoreDep) -> ServiceRead:
    try:
        service = await store.get_service(service_id)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return service_response(service)


@router.get(
    "/services/{service_id}/checks",
    response_model=list[CheckRecord],
    tags=["services"],
)
async def list_service_checks(
    service_id: str,
    store: StoreDep,
    limit: int = 50,
) -> list[CheckRecord]:
    try:
        return await store.list_checks(service_id, limit=min(max(limit, 1), 200))
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/services/{service_id}", response_model=ServiceRead, tags=["services"])
async def update_service(
    service_id: str,
    payload: ServiceUpdate,
    store: StoreDep,
) -> ServiceRead:
    try:
        service = await store.update_service(service_id, payload)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return service_response(service)


@router.delete(
    "/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["services"],
)
async def delete_service(service_id: str, store: StoreDep) -> None:
    try:
        await store.delete_service(service_id)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/monitor/run", response_model=list[CheckResult], tags=["monitoring"])
async def run_monitor_now(monitor: MonitorDep) -> list[CheckResult]:
    return await monitor.run_once()


@router.get("/monitor/status", tags=["monitoring"])
async def monitor_status(monitor: MonitorDep) -> dict[str, bool]:
    return {"running": monitor.is_running}


@dashboard_router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(store: StoreDep) -> str:
    services = await store.list_services()
    rows = "\n".join(
        f"""
        <tr>
          <td>{escape(service.name)}</td>
          <td><a href="{escape(str(service.url))}" target="_blank" rel="noreferrer">{escape(str(service.url))}</a></td>
          <td><span class="status {service.status.value}">{service.status.value}</span></td>
          <td>{service.last_response_time_ms or "-"}</td>
          <td>{service.calculate_uptime_percentage() if service.calculate_uptime_percentage() is not None else "-"}</td>
          <td>{service.last_checked_at or "Never"}</td>
        </tr>
        """
        for service in services
    )

    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Sentinel Dashboard</title>
        <style>
          body {{
            margin: 0;
            font-family: Arial, sans-serif;
            color: #18212f;
            background: #f5f7fb;
          }}
          main {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 32px 20px;
          }}
          h1 {{
            margin: 0 0 20px;
            font-size: 32px;
          }}
          table {{
            width: 100%;
            border-collapse: collapse;
            background: #ffffff;
            border: 1px solid #dfe5ee;
          }}
          th, td {{
            padding: 12px 14px;
            border-bottom: 1px solid #e7ecf3;
            text-align: left;
            font-size: 14px;
          }}
          th {{
            background: #eef3f8;
            font-weight: 700;
          }}
          .status {{
            display: inline-block;
            min-width: 70px;
            padding: 4px 8px;
            border-radius: 4px;
            text-align: center;
            font-weight: 700;
          }}
          .up {{ background: #dff7e8; color: #116932; }}
          .down {{ background: #ffe2e2; color: #9b1c1c; }}
          .unknown {{ background: #edf0f4; color: #4b5563; }}
        </style>
      </head>
      <body>
        <main>
          <h1>Sentinel</h1>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>URL</th>
                <th>Status</th>
                <th>Response ms</th>
                <th>Uptime %</th>
                <th>Last checked</th>
              </tr>
            </thead>
            <tbody>
              {rows or '<tr><td colspan="6">No services configured.</td></tr>'}
            </tbody>
          </table>
        </main>
      </body>
    </html>
    """
