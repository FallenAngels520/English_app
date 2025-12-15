from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Row

from .models import DashboardFilters, EventRecord, MembershipRecord


class DashboardDataRepository:
    """
    Interface for loading dashboard data.

    Concrete implementations should return events + memberships scoped to the
    provided filters. The SQL version below only restricts by the time window
    to remain database-agnostic and performs attribute filtering inside Python.
    """

    def load(self, filters: DashboardFilters) -> Tuple[Sequence[EventRecord], Sequence[MembershipRecord]]:
        raise NotImplementedError


class SQLDashboardRepository(DashboardDataRepository):
    """
    Load events/memberships from the normalized schema described in dashboard.md.

    Expected tables:
      - events(id, user_id, event_name, event_time, properties_json)
      - memberships(user_id, plan_type, start_at, expire_at, status, amount, order_id)
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def load(self, filters: DashboardFilters) -> Tuple[Sequence[EventRecord], Sequence[MembershipRecord]]:
        return self._load_events(filters), self._load_memberships(filters)

    def _load_events(self, filters: DashboardFilters) -> Sequence[EventRecord]:
        query = text(
            """
            SELECT id, user_id, event_name, event_time, properties_json
            FROM events
            WHERE event_time >= :start AND event_time < :end
            ORDER BY event_time ASC
            """
        )
        params = {"start": filters.start, "end": filters.end}
        with self.engine.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(self._row_to_event(row) for row in rows)

    def _load_memberships(self, filters: DashboardFilters) -> Sequence[MembershipRecord]:
        query = text(
            """
            SELECT user_id, plan_type, start_at, expire_at, status, COALESCE(amount, 0) as amount, order_id
            FROM memberships
            WHERE (start_at >= :start AND start_at < :end)
               OR (expire_at >= :start AND expire_at < :end)
            """
        )
        params = {"start": filters.start, "end": filters.end}
        with self.engine.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(self._row_to_membership(row) for row in rows)

    @staticmethod
    def _row_to_event(row: Row) -> EventRecord:
        properties = row.properties_json
        if isinstance(properties, str):
            try:
                properties = json.loads(properties)
            except json.JSONDecodeError:
                properties = {}
        elif properties is None:
            properties = {}
        return EventRecord(
            id=str(row.id),
            user_id=row.user_id,
            event_name=row.event_name,
            event_time=row.event_time,
            properties=properties,
        )

    @staticmethod
    def _row_to_membership(row: Row) -> MembershipRecord:
        return MembershipRecord(
            user_id=str(row.user_id),
            plan_type=str(row.plan_type),
            start_at=row.start_at,
            expire_at=row.expire_at,
            status=str(row.status),
            amount=float(row.amount or 0),
            order_id=row.order_id,
        )


@dataclass(frozen=True)
class RepositoryConfig:
    database_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "RepositoryConfig":
        return cls(database_url=os.getenv("DATA_DASHBOARD_DATABASE_URL"))


def build_repository_from_env(config: Optional[RepositoryConfig] = None) -> Optional[DashboardDataRepository]:
    cfg = config or RepositoryConfig.from_env()
    if cfg.database_url:
        engine = create_engine(cfg.database_url)
        return SQLDashboardRepository(engine)
    return None
