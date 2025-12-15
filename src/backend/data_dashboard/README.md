# Data Dashboard Toolkit

The `data_dashboard` package implements the backend aggregation layer described in
`dashboard.md`. It ships three pieces:

1. **`models.py`** - Dataclasses for the raw event/membership inputs plus the card/trend/table/funnel payloads that the frontend consumes.
2. **`dataset.py`** - Utilities that filter/segment the unified `events` + `memberships` streams with the canonical timezone and attribute filters (channel, region, platform, etc.).
3. **`service.py`** - `DataDashboardService`, which wires the requirements into five dashboard sections (Executive, Growth, Monetization, Learning, Ops) and outputs a `DashboardResult`.
4. **`repository.py`** - Data access layer that reads from the normalized `events`/`memberships` tables (or falls back to inline payloads) so the service is fed with real telemetry.
5. **`server.py`** - A FastAPI app that exposes `/dashboard` for the frontend/BI tools.

## Sample Usage

```python
from datetime import datetime, timedelta
from backend.data_dashboard import (
    DataDashboardService,
    DashboardFilters,
    EventRecord,
    MembershipRecord,
)

events = [
    EventRecord(
        id="evt-1",
        user_id="user-1",
        event_name="user_registered",
        event_time=datetime(2025, 12, 10, 8, 15),
        properties={"channel": "organic", "platform": "ios"},
    ),
    EventRecord(
        id="evt-2",
        user_id="user-1",
        event_name="lesson_completed",
        event_time=datetime(2025, 12, 10, 8, 45),
        properties={"course_id": "starter", "duration_seconds": 420},
    ),
]

memberships = [
    MembershipRecord(
        user_id="user-1",
        plan_type="monthly",
        start_at=datetime(2025, 12, 10, 10, 0),
        expire_at=datetime(2026, 1, 10, 10, 0),
        status="active",
        amount=12.99,
    )
]

service = DataDashboardService(events=events, memberships=memberships)
filters = DashboardFilters(
    start=datetime(2025, 12, 10),
    end=datetime(2025, 12, 17),
    channel="organic",
)

dashboard = service.build(filters)
print(dashboard.as_dict()["executive"]["cards"])
```

The example demonstrates how to:

- ingest raw events + memberships,
- scope a query to a time range + channel, and
- retrieve serialisable aggregates for the frontend.

Every metric in `dashboard.md` is backed by a helper inside `DataDashboardService`; extend these in-place as new KPIs emerge (for example, adding a new generator stage to the ops tab).

## FastAPI Endpoint

Run the dashboard API alongside the LangGraph agent:

```bash
uv run uvicorn backend.data_dashboard.server:app --app-dir src --reload --port 8100
```

Configure the database connection in `.env`:

```ini
DATA_DASHBOARD_DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname
```

The SQL repository expects the `events` / `memberships` tables sketched in `dashboard.md`. If the env var is missing, you can still hit the API by providing inline telemetry:

```bash
curl -X POST http://127.0.0.1:8100/dashboard ^
  -H "Content-Type: application/json" ^
  -d @payload.json
```

Minimal payload example (`payload.json`):

```json
{
  "start": "2025-12-10T00:00:00Z",
  "end": "2025-12-12T00:00:00Z",
  "events": [
    {
      "id": "evt-1",
      "user_id": "user-1",
      "event_name": "user_registered",
      "event_time": "2025-12-10T08:15:00Z",
      "properties": {"channel": "organic"}
    }
  ],
  "memberships": [
    {
      "user_id": "user-1",
      "plan_type": "monthly",
      "start_at": "2025-12-10T10:00:00Z",
      "expire_at": "2026-01-10T10:00:00Z",
      "status": "active",
      "amount": 12.99
    }
  ]
}
```

The response embeds `data` (matching `DashboardResult.as_dict()`) and `source` to signal whether the aggregates came from the SQL repository or inline data.
