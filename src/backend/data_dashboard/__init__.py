"""
Backend data dashboard helpers.

This package converts the requirements captured in ``dashboard.md`` into
structured Python utilities that can ingest raw event and membership data and
emit the aggregates needed by the frontend dashboards.
"""

from .models import (  # noqa: F401
    CardMetric,
    DashboardFilters,
    DashboardResult,
    DashboardSection,
    EventRecord,
    FunnelBreakdown,
    FunnelStage,
    LeaderboardRow,
    MembershipRecord,
    TrendPoint,
    TrendSeries,
)
from .repository import (  # noqa: F401
    DashboardDataRepository,
    RepositoryConfig,
    SQLDashboardRepository,
    build_repository_from_env,
)
from .service import DataDashboardService  # noqa: F401
