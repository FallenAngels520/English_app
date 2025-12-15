from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from .models import DashboardFilters, EventRecord, MembershipRecord
from .repository import DashboardDataRepository, build_repository_from_env
from .service import DataDashboardService

app = FastAPI(title="English App Data Dashboard API", version="0.1.0")
repository: Optional[DashboardDataRepository] = build_repository_from_env()


class EventPayload(BaseModel):
    id: str
    user_id: Optional[str] = None
    event_name: str
    event_time: datetime
    properties: Dict[str, Any] = Field(default_factory=dict)


class MembershipPayload(BaseModel):
    user_id: str
    plan_type: str
    start_at: datetime
    expire_at: datetime
    status: str
    amount: float = 0.0
    order_id: Optional[str] = None


class DashboardRequest(BaseModel):
    start: datetime
    end: datetime
    timezone: str = "Europe/Berlin"
    comparison_days: int = 7
    cohort_size_days: int = 7
    retention_days: Sequence[int] = Field(default_factory=lambda: (1, 7, 30))
    channel: Optional[str] = None
    region: Optional[str] = None
    locale: Optional[str] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None
    events: Optional[List[EventPayload]] = None
    memberships: Optional[List[MembershipPayload]] = None

    @validator("end")
    def _validate_range(cls, end: datetime, values: Dict[str, Any]) -> datetime:
        start = values.get("start")
        if start and end <= start:
            raise ValueError("end must be greater than start")
        return end


class DashboardResponse(BaseModel):
    data: Dict[str, Any]
    source: str


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/dashboard", response_model=DashboardResponse)
async def dashboard_endpoint(request: DashboardRequest) -> DashboardResponse:
    filters = DashboardFilters(
        start=request.start,
        end=request.end,
        timezone=request.timezone,
        channel=request.channel,
        region=request.region,
        locale=request.locale,
        platform=request.platform,
        app_version=request.app_version,
        comparison_days=request.comparison_days,
        cohort_size_days=request.cohort_size_days,
        retention_days=tuple(request.retention_days),
    )

    events, memberships, source = await _load_dataset(filters, request)
    if not events and not memberships:
        raise HTTPException(status_code=400, detail="No data available for the requested window.")

    service = DataDashboardService(events=events, memberships=memberships)
    dashboard = service.build(filters)
    return DashboardResponse(data=dashboard.as_dict(), source=source)


async def _load_dataset(
    filters: DashboardFilters,
    request: DashboardRequest,
) -> Tuple[Sequence[EventRecord], Sequence[MembershipRecord], str]:
    if repository is not None:
        events, memberships = repository.load(filters)
        return events, memberships, "database"

    if request.events is None or request.memberships is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "DATA_DASHBOARD_DATABASE_URL is not configured; "
                "supply events+memberships in the request body for ad-hoc queries."
            ),
        )

    return (
        tuple(_convert_event_payload(payload) for payload in request.events),
        tuple(_convert_membership_payload(payload) for payload in request.memberships),
        "inline",
    )


def _convert_event_payload(payload: EventPayload) -> EventRecord:
    return EventRecord(
        id=payload.id,
        user_id=payload.user_id,
        event_name=payload.event_name,
        event_time=payload.event_time,
        properties=payload.properties,
    )


def _convert_membership_payload(payload: MembershipPayload) -> MembershipRecord:
    return MembershipRecord(
        user_id=payload.user_id,
        plan_type=payload.plan_type,
        start_at=payload.start_at,
        expire_at=payload.expire_at,
        status=payload.status,
        amount=payload.amount,
        order_id=payload.order_id,
    )
