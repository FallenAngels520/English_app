from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Iterator, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import DashboardFilters, EventRecord, MembershipRecord


def _coerce_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _normalize_datetime(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _event_user_key(event: EventRecord) -> Optional[str]:
    return event.user_id or event.properties.get("device_id") or event.properties.get("anonymous_id")


@dataclass
class DashboardDataset:
    events: Sequence[EventRecord]
    memberships: Sequence[MembershipRecord]

    def __post_init__(self) -> None:
        self.events = tuple(sorted(self.events, key=lambda event: event.event_time))
        self.memberships = tuple(sorted(self.memberships, key=lambda membership: membership.start_at))

    def iter_events(
        self,
        filters: DashboardFilters,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Iterator[Tuple[EventRecord, datetime]]:
        """
        Yield events that fall inside the requested window and match the filters.

        Returns tuples of (event, localized_event_time) so callers can safely use
        ``datetime.date()`` without worrying about timezone conversions.
        """

        tz = _coerce_timezone(filters.timezone)
        window_start = _normalize_datetime(start or filters.start, tz)
        window_end = _normalize_datetime(end or filters.end, tz)
        filter_map = filters.as_event_filters()

        for event in self.events:
            event_local_time = _normalize_datetime(event.event_time, tz)
            if not (window_start <= event_local_time < window_end):
                continue
            if not self._matches_filters(event, filter_map):
                continue
            yield event, event_local_time

    def unique_users(
        self,
        filters: DashboardFilters,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        users = {
            key
            for event, _ in self.iter_events(filters, start=start, end=end)
            if (key := _event_user_key(event)) is not None
        }
        return len(users)

    def events_per_day(
        self,
        filters: DashboardFilters,
        start: datetime,
        end: datetime,
        event_names: Optional[Sequence[str]] = None,
    ) -> Dict[datetime, int]:
        tz = _coerce_timezone(filters.timezone)
        start = _normalize_datetime(start, tz)
        end = _normalize_datetime(end, tz)
        allowed = set(event_names or [])
        daily = defaultdict(int)

        for event, localized_time in self.iter_events(filters, start=start, end=end):
            if allowed and event.event_name not in allowed:
                continue
            day_key = localized_time.replace(hour=0, minute=0, second=0, microsecond=0)
            daily[day_key] += 1

        return dict(daily)

    def group_count_by_property(
        self,
        filters: DashboardFilters,
        start: datetime,
        end: datetime,
        property_name: str,
        event_names: Optional[Sequence[str]] = None,
    ) -> Dict[str, int]:
        """
        Count how many events share the same ``property_name`` value.
        """

        totals = defaultdict(int)
        allowed = set(event_names or [])

        for event, _ in self.iter_events(filters, start=start, end=end):
            if allowed and event.event_name not in allowed:
                continue
            key = str(event.properties.get(property_name) or "unknown")
            totals[key] += 1

        return dict(totals)

    def membership_snapshot(self, at: datetime) -> Sequence[MembershipRecord]:
        """
        Return memberships considered active at the provided timestamp.
        """

        return [
            membership
            for membership in self.memberships
            if membership.status == "active" and membership.start_at <= at < membership.expire_at
        ]

    def memberships_between(self, start: datetime, end: datetime) -> Sequence[MembershipRecord]:
        return [membership for membership in self.memberships if start <= membership.start_at < end]

    @staticmethod
    def _matches_filters(event: EventRecord, filter_map: Dict[str, Optional[str]]) -> bool:
        for key, expected_value in filter_map.items():
            if expected_value is None:
                continue
            if event.properties.get(key) != expected_value:
                return False
        return True
