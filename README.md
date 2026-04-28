# Sentinel

Sentinel is a production-style FastAPI backend for monitoring external services. It tracks service uptime, response time, check history, system activity, and failure/recovery alerts.

## Features

- FastAPI REST API with Pydantic validation
- Async background monitoring with `asyncio` and `httpx`
- SQLite persistence for monitored services and historical checks
- Optional JSON seed file for initial services
- Rotating application logs
- Failure and recovery alerts with optional webhook delivery
- Basic HTML dashboard
- Automated tests with `pytest`
- Docker and Docker Compose support
- GitHub Actions CI workflow

## Project Structure

```text
sentinel/
|-- app/
|   |-- main.py
|   |-- config.py
|   |-- models/
|   |   |-- __init__.py
|   |   `-- service.py
|   |-- routes/
|   |   |-- __init__.py
|   |   `-- api.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- alert.py
|   |   |-- logger.py
|   |   |-- monitor.py
|   |   `-- storage.py
|   `-- utils/
|       |-- __init__.py
|       `-- helpers.py
|-- data/
|   `-- services.json
|-- logs/
|   `-- .gitkeep
|-- tests/
|   `-- test_api.py
|-- .github/
|   `-- workflows/
|       `-- ci.yml
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
|-- requirements-dev.txt
`-- README.md
```

Runtime files such as `data/sentinel.db`, `logs/system.log`, `.venv/`, and Python cache folders are intentionally ignored by Git.

## Setup

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Open:

- Dashboard: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/health`

Stop the server with `Ctrl+C`.

## API Examples

Create a monitored service:

```bash
curl -X POST http://127.0.0.1:8000/api/services \
  -H "Content-Type: application/json" \
  -d '{"name":"Example","url":"https://example.com","enabled":true}'
```

List services:

```bash
curl http://127.0.0.1:8000/api/services
```

Get one service:

```bash
curl http://127.0.0.1:8000/api/services/{service_id}
```

Update a service:

```bash
curl -X PATCH http://127.0.0.1:8000/api/services/{service_id} \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}'
```

Delete a service:

```bash
curl -X DELETE http://127.0.0.1:8000/api/services/{service_id}
```

Run a monitoring pass immediately:

```bash
curl -X POST http://127.0.0.1:8000/api/monitor/run
```

Check monitoring status:

```bash
curl http://127.0.0.1:8000/api/monitor/status
```

View check history:

```bash
curl http://127.0.0.1:8000/api/services/{service_id}/checks
```

## Configuration

Settings can be overridden with environment variables using the `SENTINEL_` prefix.

| Variable | Default | Description |
| --- | --- | --- |
| `SENTINEL_DATA_FILE` | `data/services.json` | Optional JSON seed file |
| `SENTINEL_DATABASE_FILE` | `data/sentinel.db` | SQLite database path |
| `SENTINEL_LOG_FILE` | `logs/system.log` | Application log path |
| `SENTINEL_MONITOR_INTERVAL_SECONDS` | `30` | Background check interval |
| `SENTINEL_REQUEST_TIMEOUT_SECONDS` | `5.0` | HTTP request timeout |
| `SENTINEL_ALERT_COOLDOWN_SECONDS` | `300` | Alert cooldown per service |
| `SENTINEL_ALERT_WEBHOOK_URL` | unset | Optional webhook URL for alerts |

## Tests

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the test suite:

```bash
pytest
```

## Docker

```bash
docker compose up --build
```

The app will be available at `http://127.0.0.1:8000`.

## GitHub Readiness

Before pushing:

```bash
pytest
```

The repository is configured to ignore local runtime files, virtual environments, logs, databases, and Python cache files. GitHub Actions will run the test suite on pushes and pull requests.

## Future Improvements

- PostgreSQL storage option for production deployments
- Authentication for protected service management endpoints
- Slack, Discord, or email alert integrations
- Dashboard charts for latency and uptime trends
