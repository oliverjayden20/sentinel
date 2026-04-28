# Sentinel Interview Q&A

Use this as a spoken practice script for explaining Sentinel in a junior backend interview. The answers are intentionally direct and honest: they explain what the project does, why it was designed this way, and what could be improved next.

## Short Project Pitch

**Interviewer:** Give me a quick overview of this project.

**You:** Sentinel is a FastAPI backend that monitors external URLs. You can add services through a REST API, and the app checks them in the background to track whether they are up or down, their response time, uptime percentage, and historical check results. It uses SQLite for persistence, Python logging for system activity, optional webhook alerts for failures and recoveries, and it includes tests, Docker support, and GitHub Actions CI.

**Follow-up answer:** I built it to practice production-style backend structure: separating routes, models, services, configuration, persistence, background jobs, and tests instead of putting everything into one file.

## Project Overview And Architecture

**Interviewer:** What problem does Sentinel solve?

**You:** It solves a basic uptime-monitoring problem. If I have services like websites or APIs that I care about, Sentinel lets me register them, monitor them repeatedly, store their status history, and trigger alerts when they fail.

**Interviewer:** How is the project organized?

**You:** The project is split by responsibility. `routes` contains the API endpoints, `models` contains Pydantic data models, `services` contains business logic like monitoring, storage, logging, and alerts, and `utils` contains response helpers. That keeps the API layer thin and makes the core logic easier to test and replace.

**Interviewer:** Why not put everything in `main.py`?

**You:** For a tiny demo that would work, but it does not scale well. I wanted this to look closer to a real backend project. `main.py` wires the app together, while the actual behavior lives in focused modules. That makes it easier to maintain, test, and explain.

## FastAPI Routing And App Startup

**Interviewer:** How does the FastAPI app start?

**You:** The app uses a `create_app(start_monitor=True)` factory in `app/main.py`. Inside the FastAPI lifespan function, it creates the SQLite-backed `ServiceStore`, the `AlertManager`, and the `MonitoringEngine`. When the app starts, the monitor starts running in the background. When the app shuts down, the monitor is stopped cleanly.

**Interviewer:** Why use an app factory?

**You:** The app factory makes the app easier to test. In tests, I can call `create_app(start_monitor=False)` so the API is available without starting the background monitoring loop. That keeps tests predictable and avoids making real external HTTP checks during normal API tests.

**Interviewer:** How do routes access the store and monitor?

**You:** They use FastAPI dependencies that read `request.app.state.service_store` and `request.app.state.monitor`. The app state is populated during startup, so the route functions do not create their own storage or monitoring objects.

## Pydantic Models And Validation

**Interviewer:** What do you use Pydantic for?

**You:** Pydantic validates incoming API data and shapes outgoing responses. For example, `ServiceCreate` validates that a service has a non-empty name and a valid HTTP URL. `ServiceUpdate` allows partial updates. `ServiceRead` adds the calculated uptime percentage to the response.

**Interviewer:** What validation rules did you add?

**You:** Service names must be between 1 and 120 characters, and whitespace-only names are rejected. URLs use Pydantic's `HttpUrl`, so invalid URLs are rejected automatically. The status is constrained to an enum: `unknown`, `up`, or `down`.

**Interviewer:** How is uptime percentage calculated?

**You:** Each service stores `uptime_checks` and `failed_checks`. If there are no checks yet, uptime percentage is `None`. Otherwise, it calculates successful checks divided by total checks and rounds the result to two decimal places.

## Async Monitoring Engine

**Interviewer:** How does the monitoring engine work?

**You:** The `MonitoringEngine` runs as an asyncio background task. It loads enabled services from storage, uses `httpx.AsyncClient` to check them, records the response time, marks the service as up or down, saves the latest status, records a historical check row, and then triggers alert logic if needed.

**Interviewer:** Why use async code here?

**You:** Monitoring URLs is mostly network I/O. Async code lets the app check multiple services concurrently without blocking the server thread while waiting for HTTP responses. That is a good fit for uptime checks.

**Interviewer:** How does it decide if a service is up or down?

**You:** It sends a GET request to the service URL. If the request succeeds and the response does not raise an HTTP error, the service is marked `up`. If there is an exception, timeout, connection error, or failing status code, the service is marked `down`, and the error message is stored.

**Interviewer:** How does response time get measured?

**You:** It uses `time.perf_counter()` before and after the HTTP request, then converts the elapsed time to milliseconds. That value is stored as `last_response_time_ms` and also saved in the check history.

**Interviewer:** What happens if one monitoring cycle fails?

**You:** The monitor catches unexpected exceptions around each cycle and logs them with `logger.exception`. That prevents one bad cycle from killing the background monitoring task.

## SQLite Persistence And Check History

**Interviewer:** Why did you use SQLite?

**You:** I started with JSON storage, but SQLite is a better step toward a real backend. It gives structured tables, query support, foreign keys, and persistent check history while staying simple to run locally without a separate database server.

**Interviewer:** What is stored in the database?

**You:** There are two main tables. The `services` table stores the current service state, such as name, URL, enabled flag, status, latest response time, total checks, failed checks, and timestamps. The `service_checks` table stores historical check records for each service.

**Interviewer:** What is `services.json` still used for?

**You:** It is used as an optional seed file. If the SQLite database is empty, the store can load initial services from `data/services.json`. Runtime data goes into SQLite.

**Interviewer:** How do you view check history?

**You:** Through this endpoint:

```text
GET /api/services/{service_id}/checks
```

It returns recent historical check records for that service, ordered by newest first. The route also clamps the limit between 1 and 200.

**Interviewer:** How do deletes affect check history?

**You:** The database uses a foreign key from `service_checks` to `services` with cascade delete. When a service is deleted, its check history is deleted too.

## Logging And Alerting

**Interviewer:** How does logging work?

**You:** Logging is configured in `app/services/logger.py`. It uses Python's standard logging module with a rotating file handler. Logs go to `logs/system.log`, and the logger also writes to the console. Rotation helps prevent the log file from growing forever.

**Interviewer:** Why are logs ignored by Git?

**You:** Logs are runtime output. They change constantly, can become large, and may contain sensitive data. The repo keeps `logs/.gitkeep` so the folder exists, but ignores actual `.log` files.

**Interviewer:** How do alerts work?

**You:** The `AlertManager` logs a warning when a service goes down and logs a recovery message when it comes back up. It also supports an optional webhook URL using `SENTINEL_ALERT_WEBHOOK_URL`, so failure and recovery events can be posted to another service.

**Interviewer:** What is the alert cooldown for?

**You:** The cooldown prevents repeated alerts for the same service during a continuous outage. Without it, a service that stays down could generate an alert every monitoring interval.

## API Endpoints And Dashboard

**Interviewer:** What are the main API endpoints?

**You:** The main endpoints are:

```text
GET    /api/health
GET    /api/services
POST   /api/services
GET    /api/services/{service_id}
PATCH  /api/services/{service_id}
DELETE /api/services/{service_id}
GET    /api/services/{service_id}/checks
POST   /api/monitor/run
GET    /api/monitor/status
```

**Interviewer:** What does `/api/monitor/run` do?

**You:** It runs one monitoring pass immediately instead of waiting for the background interval. That is useful for testing or manually refreshing service statuses.

**Interviewer:** What is the dashboard?

**You:** The root route `/` returns a simple HTML dashboard showing service name, URL, status, latest response time, uptime percentage, and last checked time. It is intentionally basic, but it makes the backend easier to demonstrate visually.

**Interviewer:** Did you handle HTML escaping?

**You:** Yes. The dashboard escapes service names and URLs before inserting them into HTML. That avoids directly rendering user-provided strings as raw HTML.

## Testing Strategy

**Interviewer:** What automated tests are included?

**You:** The tests use `pytest` and FastAPI's `TestClient`. They cover service CRUD behavior, validation errors for bad payloads, and the check history endpoint.

**Interviewer:** How do the tests avoid touching your real database?

**You:** The tests use `tmp_path` and environment variables to point Sentinel at a temporary SQLite database and temporary seed file. They also clear the settings cache before creating the app, so the app picks up the test configuration.

**Interviewer:** Why is `start_monitor=False` used in tests?

**You:** It prevents the background monitoring loop from running during API tests. That keeps tests deterministic and avoids real network calls.

**Interviewer:** What tests would you add next?

**You:** I would add tests for the monitoring engine itself by mocking HTTP responses, tests for alert cooldown behavior, tests for webhook delivery failures, and tests for check history after a successful manual monitoring run.

## Docker, CI, And GitHub Readiness

**Interviewer:** What does Docker add to this project?

**You:** Docker makes the app easier to run in a consistent environment. The `Dockerfile` installs dependencies, copies the app, exposes port 8000, and starts Uvicorn. `docker-compose.yml` maps the app port and mounts `data` and `logs` so the database and logs persist locally.

**Interviewer:** What does GitHub Actions do?

**You:** The CI workflow installs Python 3.11, installs development dependencies, and runs `pytest` on pushes and pull requests. That gives a basic automated quality check before changes are merged.

**Interviewer:** Why split `requirements.txt` and `requirements-dev.txt`?

**You:** `requirements.txt` contains runtime dependencies needed to run the app. `requirements-dev.txt` includes those plus development tools like `pytest`. That keeps production installs smaller and clearer.

## Tradeoffs, Limitations, And Future Improvements

**Interviewer:** What are the main tradeoffs in this project?

**You:** SQLite is simple and good for local development, but for a production multi-user or multi-instance deployment I would move to PostgreSQL. The dashboard is useful for demonstration but basic. Alerts support logging and webhooks, but I would add integrations like Slack, Discord, or email.

**Interviewer:** What is missing before this would be production-ready?

**You:** Authentication is the biggest missing piece because service management endpoints should not be public. I would also add rate limiting, better structured logging, more complete monitoring tests, migrations, and a real frontend dashboard with charts.

**Interviewer:** What would you improve first?

**You:** I would add authentication and more monitoring tests first. Authentication protects the API, and monitoring tests would prove the most important backend behavior: checking services, saving history, and triggering alerts.

**Interviewer:** If you deployed this, what would you watch?

**You:** I would watch application logs, error rates, failed monitoring cycles, database growth, webhook failures, and response time trends. I would also add health checks and alerts for the Sentinel app itself.

## Ownership Questions

**Interviewer:** What part of the project are you most confident explaining?

**You:** The flow from API creation to background monitoring. A service is created through the REST API, validated with Pydantic, saved in SQLite, loaded by the monitoring engine, checked asynchronously with `httpx`, updated with latest status and response time, recorded into check history, and then passed through alert logic.

**Interviewer:** What was the most important design decision?

**You:** Separating the project into clear layers was the most important decision. It keeps route handlers focused on HTTP behavior, storage focused on persistence, and the monitor focused on checking services. That separation makes the project easier to test and extend.

**Interviewer:** How would you describe this project on a resume?

**You:** I would say: "Built Sentinel, a FastAPI service-monitoring backend with async URL checks, SQLite persistence, uptime metrics, historical check records, rotating logs, webhook-capable alerts, Docker support, and pytest/GitHub Actions CI."

## Quick Practice Answers

**What is Sentinel?**  
Sentinel is a FastAPI backend that monitors external services and tracks uptime, response time, check history, logs, and alerts.

**Why FastAPI?**  
FastAPI gives fast API development, automatic OpenAPI docs, async support, and strong Pydantic validation.

**Why SQLite?**  
SQLite is simple to run locally while still giving structured persistence and queryable history.

**Why async monitoring?**  
URL checks are network I/O, so async lets the app check multiple services concurrently without blocking.

**How are failures detected?**  
A service is marked down if the HTTP request raises an error, times out, cannot connect, or returns a failing HTTP status.

**How are alerts handled?**  
Failures and recoveries are logged, and an optional webhook can receive alert payloads. A cooldown prevents repeated alerts during the same outage.

**What do the tests cover?**  
They cover CRUD behavior, request validation, and the check history endpoint using a temporary test database.

**What would you improve next?**  
Authentication, stronger monitoring tests, PostgreSQL support, and richer alert integrations.
