from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class EventRecord:
    """
    Atomic interaction emitted by the product instrumentation.

    ``properties`` mirrors the flexible JSONB payload proposed in the
    specification and can contain channel/app_version/course/word level detail.
    """

    id: str
    user_id: Optional[str]
    event_name: str
    event_time: datetime
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MembershipRecord:
    """
    Snapshot of a membership/subscription document.

    ``amount`` is used for ARPU/AOV/ARPPU style calculations and defaults to 0
    when the upstream data source does not supply a value yet.
    """

    user_id: str
    plan_type: str
    start_at: datetime
    expire_at: datetime
    status: str
    amount: float = 0.0
    order_id: Optional[str] = None


@dataclass(frozen=True)
class DashboardFilters:
    """
    Generic filters reused by all dashboard pages.

    ``start`` is inclusive and ``end`` is exclusive. ``timezone`` defaults to
    Europe/Berlin per the requirements. Optional categorical filters align with
    the growth tab needs (channel/region/locale/client/app_version). The
    ``comparison_days`` window defines how deltas are calculated for card
    metrics.
    """

    start: datetime
    end: datetime
    timezone: str = "Europe/Berlin"
    channel: Optional[str] = None
    region: Optional[str] = None
    locale: Optional[str] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None
    comparison_days: int = 7
    cohort_size_days: int = 7
    retention_days: Sequence[int] = (1, 7, 30)

    def as_event_filters(self) -> Dict[str, Optional[str]]:
        return {
            "channel": self.channel,
            "region": self.region,
            "locale": self.locale,
            "platform": self.platform,
            "app_version": self.app_version,
        }


@dataclass(frozen=True)
class CardMetric:
    key: str
    label: str
    value: float
    unit: Optional[str] = None
    delta_percent: Optional[float] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class TrendPoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class TrendSeries:
    name: str
    points: Iterable[TrendPoint]
    comparison_points: Optional[Iterable[TrendPoint]] = None
    unit: Optional[str] = None


@dataclass(frozen=True)
class FunnelStage:
    label: str
    count: int
    conversion_rate: Optional[float] = None


@dataclass(frozen=True)
class FunnelBreakdown:
    name: str
    stages: Sequence[FunnelStage]


@dataclass(frozen=True)
class LeaderboardRow:
    label: str
    metrics: Dict[str, float]


@dataclass(frozen=True)
class DashboardSection:
    cards: Sequence[CardMetric] = field(default_factory=list)
    trends: Sequence[TrendSeries] = field(default_factory=list)
    funnels: Sequence[FunnelBreakdown] = field(default_factory=list)
    tables: Dict[str, Sequence[LeaderboardRow]] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardResult:
    executive: DashboardSection
    growth: DashboardSection
    monetization: DashboardSection
    learning: DashboardSection
    ops: DashboardSection

    def as_dict(self) -> Dict[str, Any]:
        """
        Convert the nested dataclasses into a JSON-serialisable structure.

        FastAPI/Next.js callers can reuse this to ship the aggregates to the UI
        without taking a dependency on dataclasses.
        """

        def _serialize(obj: Any) -> Any:
            if isinstance(obj, DashboardResult):
                return {
                    "executive": _serialize(obj.executive),
                    "growth": _serialize(obj.growth),
                    "monetization": _serialize(obj.monetization),
                    "learning": _serialize(obj.learning),
                    "ops": _serialize(obj.ops),
                }
            if isinstance(obj, DashboardSection):
                return {
                    "cards": [_serialize(card) for card in obj.cards],
                    "trends": [_serialize(trend) for trend in obj.trends],
                    "funnels": [_serialize(funnel) for funnel in obj.funnels],
                    "tables": {
                        name: [_serialize(row) for row in rows]
                        for name, rows in obj.tables.items()
                    },
                }
            if isinstance(obj, CardMetric):
                return {
                    "key": obj.key,
                    "label": obj.label,
                    "value": obj.value,
                    "unit": obj.unit,
                    "deltaPercent": obj.delta_percent,
                    "description": obj.description,
                }
            if isinstance(obj, TrendSeries):
                return {
                    "name": obj.name,
                    "unit": obj.unit,
                    "points": [_serialize(point) for point in obj.points],
                    "comparisonPoints": (
                        None
                        if obj.comparison_points is None
                        else [_serialize(point) for point in obj.comparison_points]
                    ),
                }
            if isinstance(obj, TrendPoint):
                return {"timestamp": obj.timestamp.isoformat(), "value": obj.value}
            if isinstance(obj, FunnelBreakdown):
                return {
                    "name": obj.name,
                    "stages": [_serialize(stage) for stage in obj.stages],
                }
            if isinstance(obj, FunnelStage):
                return {
                    "label": obj.label,
                    "count": obj.count,
                    "conversionRate": obj.conversion_rate,
                }
            if isinstance(obj, LeaderboardRow):
                return {"label": obj.label, "metrics": obj.metrics}
            if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
                return [_serialize(item) for item in obj]
            return obj

        return _serialize(self)
