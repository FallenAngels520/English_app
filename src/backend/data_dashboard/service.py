from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .dataset import DashboardDataset
from .models import (
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


ENGAGEMENT_EVENTS = {
    "app_open",
    "chat",
    "practice_started",
    "practice_done",
    "lesson_started",
    "lesson_completed",
    "study_session",
}
PAYWALL_VIEW_EVENTS = {"subscribe_view", "paywall_view"}
PAYWALL_CTA_EVENTS = {"paywall_cta_click"}
PAYMENT_EVENTS = {"pay_success"}
SYSTEM_EVENTS = {
    "model_invoke",
    "image_generation",
    "tts_generation",
}


def _calc_delta(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def _build_card(
    key: str,
    label: str,
    value: float,
    previous: float = 0.0,
    unit: Optional[str] = None,
    description: Optional[str] = None,
) -> CardMetric:
    return CardMetric(
        key=key,
        label=label,
        value=value,
        unit=unit,
        delta_percent=_calc_delta(value, previous),
        description=description,
    )


def _daterange(start: datetime, end: datetime, step_days: int = 1) -> Iterable[datetime]:
    cursor = start
    while cursor < end:
        yield cursor
        cursor += timedelta(days=step_days)


@dataclass
class _TimeWindows:
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime
    primary_day_start: datetime
    primary_day_end: datetime
    previous_day_start: datetime
    previous_day_end: datetime


class DataDashboardService:
    """
    Aggregates product analytics for the dashboard described in ``dashboard.md``.
    """

    def __init__(
        self,
        events: Sequence[EventRecord],
        memberships: Sequence[MembershipRecord],
    ) -> None:
        self.dataset = DashboardDataset(events=events, memberships=memberships)

    def build(self, filters: DashboardFilters) -> DashboardResult:
        windows = self._compute_windows(filters)
        executive = self._build_executive(filters, windows)
        growth = self._build_growth(filters, windows)
        monetization = self._build_monetization(filters, windows)
        learning = self._build_learning(filters, windows)
        ops = self._build_ops(filters, windows)
        return DashboardResult(
            executive=executive,
            growth=growth,
            monetization=monetization,
            learning=learning,
            ops=ops,
        )

    def _compute_windows(self, filters: DashboardFilters) -> _TimeWindows:
        window_delta = filters.end - filters.start
        previous_start = filters.start - window_delta
        previous_end = filters.end - window_delta
        day_delta = timedelta(days=1)
        primary_day_start = max(filters.start, filters.end - day_delta)
        primary_day_end = filters.end
        previous_day_start = primary_day_start - day_delta
        previous_day_end = primary_day_start

        return _TimeWindows(
            current_start=filters.start,
            current_end=filters.end,
            previous_start=previous_start,
            previous_end=previous_end,
            primary_day_start=primary_day_start,
            primary_day_end=primary_day_end,
            previous_day_start=previous_day_start,
            previous_day_end=previous_day_end,
        )

    def _build_executive(self, filters: DashboardFilters, windows: _TimeWindows) -> DashboardSection:
        cards = self._build_executive_cards(filters, windows)
        trends = self._build_executive_trends(filters, windows)
        tables = self._build_executive_tables(filters, windows)
        funnels = self._build_executive_funnels(filters, windows)
        return DashboardSection(cards=cards, trends=trends, tables=tables, funnels=funnels)

    def _build_executive_cards(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[CardMetric]:
        day_users = self.dataset.unique_users(filters, start=windows.primary_day_start, end=windows.primary_day_end)
        previous_day_users = self.dataset.unique_users(
            filters, start=windows.previous_day_start, end=windows.previous_day_end
        )

        wau_start = windows.primary_day_end - timedelta(days=7)
        wau_prev_start = wau_start - timedelta(days=7)
        wau = self.dataset.unique_users(filters, start=wau_start, end=windows.primary_day_end)
        wau_prev = self.dataset.unique_users(filters, start=wau_prev_start, end=wau_start)

        mau_start = windows.primary_day_end - timedelta(days=30)
        mau_prev_start = mau_start - timedelta(days=30)
        mau = self.dataset.unique_users(filters, start=mau_start, end=windows.primary_day_end)
        mau_prev = self.dataset.unique_users(filters, start=mau_prev_start, end=mau_start)

        new_users = sum(
            1
            for event, _ in self.dataset.iter_events(filters, start=windows.primary_day_start, end=windows.primary_day_end)
            if event.event_name in {"user_registered", "new_user"}
        )
        new_users_prev = sum(
            1
            for event, _ in self.dataset.iter_events(
                filters, start=windows.previous_day_start, end=windows.previous_day_end
            )
            if event.event_name in {"user_registered", "new_user"}
        )

        active_members = len(self.dataset.membership_snapshot(windows.primary_day_end))
        active_members_prev = len(self.dataset.membership_snapshot(windows.previous_day_end))

        new_members = len(self.dataset.memberships_between(windows.primary_day_start, windows.primary_day_end))
        new_members_prev = len(self.dataset.memberships_between(windows.previous_day_start, windows.previous_day_end))

        conversion_rate = new_members / day_users * 100 if day_users else 0.0
        conversion_rate_prev = new_members_prev / previous_day_users * 100 if previous_day_users else 0.0

        renewal_rate, renewal_rate_prev = self._calculate_renewal_rates(filters, windows)
        arpu, arpu_prev, arppu, arppu_prev = self._calculate_revenue_metrics(filters, windows)
        avg_study_minutes, avg_study_minutes_prev = self._calculate_study_minutes(filters, windows)
        avg_practice_count, avg_practice_count_prev = self._calculate_practice_count(filters, windows)
        d1_retention, d1_retention_prev = self._calculate_retention(filters, 1, windows)

        cards = [
            _build_card("dau", "DAU", day_users, previous_day_users),
            _build_card("wau", "WAU", wau, wau_prev),
            _build_card("mau", "MAU", mau, mau_prev),
            _build_card("new_users", "New Users", new_users, new_users_prev),
            _build_card("active_members", "Active Members", active_members, active_members_prev),
            _build_card("new_members", "New Members", new_members, new_members_prev),
            _build_card("member_cvr", "Member Conversion Rate", conversion_rate, conversion_rate_prev, unit="%"),
            _build_card("renewal_rate", "Renewal Rate", renewal_rate, renewal_rate_prev, unit="%"),
            _build_card("arpu", "ARPU", arpu, arpu_prev, unit="$"),
            _build_card("arppu", "ARPPU", arppu, arppu_prev, unit="$"),
            _build_card("avg_study_minutes", "Avg Study Minutes", avg_study_minutes, avg_study_minutes_prev),
            _build_card("avg_practice_count", "Avg Practice Count", avg_practice_count, avg_practice_count_prev),
            _build_card("d1_retention", "D1 Retention", d1_retention, d1_retention_prev, unit="%"),
        ]
        return cards

    def _build_executive_trends(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[TrendSeries]:
        trends: List[TrendSeries] = []
        dau_points, dau_prev_points = self._daily_active_users_series(filters, windows)
        trends.append(
            TrendSeries(
                name="DAU",
                points=dau_points,
                comparison_points=dau_prev_points,
                unit="users",
            )
        )

        trends.append(self._daily_event_series(filters, windows, {"user_registered", "new_user"}, "New Users"))
        trends.append(self._daily_membership_series(filters, windows, "New Members"))
        trends.append(self._learning_completion_trend(filters, windows))
        return trends

    def _build_executive_tables(self, filters: DashboardFilters, windows: _TimeWindows) -> Dict[str, Sequence[LeaderboardRow]]:
        return {
            "top_courses": self._top_courses(filters, windows),
            "top_words": self._top_words(filters, windows),
            "top_channels": self._top_channels(filters, windows),
        }

    def _build_executive_funnels(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[FunnelBreakdown]:
        return [self._membership_funnel(filters, windows), self._learning_funnel(filters, windows)]

    def _daily_active_users_series(
        self, filters: DashboardFilters, windows: _TimeWindows
    ) -> Tuple[List[TrendPoint], List[TrendPoint]]:
        current_points: List[TrendPoint] = []
        previous_points: List[TrendPoint] = []
        window_delta = windows.current_end - windows.current_start
        for day in _daterange(windows.current_start, windows.current_end):
            current_points.append(
                TrendPoint(
                    timestamp=day,
                    value=self.dataset.unique_users(filters, start=day, end=day + timedelta(days=1)),
                )
            )
        for day in _daterange(windows.previous_start, windows.previous_end):
            previous_points.append(
                TrendPoint(
                    timestamp=day + window_delta,
                    value=self.dataset.unique_users(filters, start=day, end=day + timedelta(days=1)),
                )
            )
        return current_points, previous_points

    def _daily_event_series(
        self,
        filters: DashboardFilters,
        windows: _TimeWindows,
        event_names: Sequence[str],
        name: str,
    ) -> TrendSeries:
        points: List[TrendPoint] = []
        target_names = set(event_names)
        for day in _daterange(windows.current_start, windows.current_end):
            next_day = day + timedelta(days=1)
            value = sum(
                1
                for event, _ in self.dataset.iter_events(filters, start=day, end=next_day)
                if event.event_name in target_names
            )
            points.append(TrendPoint(timestamp=day, value=value))
        return TrendSeries(name=name, points=points, unit="events")

    def _daily_membership_series(self, filters: DashboardFilters, windows: _TimeWindows, name: str) -> TrendSeries:
        points: List[TrendPoint] = []
        for day in _daterange(windows.current_start, windows.current_end):
            next_day = day + timedelta(days=1)
            value = len(self.dataset.memberships_between(day, next_day))
            points.append(TrendPoint(timestamp=day, value=value))
        return TrendSeries(name=name, points=points, unit="memberships")

    def _learning_completion_trend(self, filters: DashboardFilters, windows: _TimeWindows) -> TrendSeries:
        points: List[TrendPoint] = []
        for day in _daterange(windows.current_start, windows.current_end):
            next_day = day + timedelta(days=1)
            started, completed = 0, 0
            for event, _ in self.dataset.iter_events(filters, start=day, end=next_day):
                if event.event_name == "lesson_started":
                    started += 1
                elif event.event_name == "lesson_completed":
                    completed += 1
            completion_rate = completed / started * 100 if started else 0.0
            points.append(TrendPoint(timestamp=day, value=completion_rate))
        return TrendSeries(name="Learning Completion Rate", points=points, unit="%")

    def _top_courses(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[LeaderboardRow]:
        stats: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for event, _ in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if event.event_name not in {"lesson_started", "lesson_completed"}:
                continue
            course_id = str(event.properties.get("course_id") or "unknown")
            if event.event_name == "lesson_started":
                stats[course_id]["started"] += 1
            if event.event_name == "lesson_completed":
                stats[course_id]["completed"] += 1
                stats[course_id]["duration_seconds"] += float(event.properties.get("duration_seconds") or 0.0)

        rows: List[LeaderboardRow] = []
        for course_id, values in stats.items():
            started = values.get("started", 0.0)
            completed = values.get("completed", 0.0)
            completion_rate = completed / started * 100 if started else 0.0
            avg_minutes = (values.get("duration_seconds", 0.0) / completed / 60) if completed else 0.0
            rows.append(
                LeaderboardRow(
                    label=course_id,
                    metrics={
                        "completions": completed,
                        "completion_rate": completion_rate,
                        "avg_minutes": avg_minutes,
                    },
                )
            )
        return sorted(rows, key=lambda row: row.metrics["completions"], reverse=True)[:10]

    def _top_words(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[LeaderboardRow]:
        stats: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for event, _ in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if event.event_name != "practice_done":
                continue
            word_id = str(event.properties.get("word_id") or "unknown")
            stats[word_id]["attempts"] += 1
            if event.properties.get("correct"):
                stats[word_id]["correct"] += 1

        rows: List[LeaderboardRow] = []
        for word_id, values in stats.items():
            attempts = values.get("attempts", 0.0)
            correct = values.get("correct", 0.0)
            accuracy = correct / attempts if attempts else 0.0
            rows.append(
                LeaderboardRow(
                    label=word_id,
                    metrics={
                        "practice_count": attempts,
                        "error_rate": (1 - accuracy) * 100,
                        "mastery_rate": accuracy * 100,
                    },
                )
            )
        return sorted(rows, key=lambda row: row.metrics["practice_count"], reverse=True)[:10]

    def _top_channels(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[LeaderboardRow]:
        channel_counts = self.dataset.group_count_by_property(
            filters,
            start=windows.current_start,
            end=windows.current_end,
            property_name="channel",
            event_names=["user_registered"],
        )
        return [
            LeaderboardRow(label=channel, metrics={"new_users": count})
            for channel, count in sorted(channel_counts.items(), key=lambda item: item[1], reverse=True)
        ][:10]

    def _membership_funnel(self, filters: DashboardFilters, windows: _TimeWindows) -> FunnelBreakdown:
        stages = {
            "active_users": 0,
            "paywall_view": 0,
            "paywall_click": 0,
            "payment_success": 0,
        }

        for event, _ in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if event.event_name in ENGAGEMENT_EVENTS:
                stages["active_users"] += 1
            if event.event_name in PAYWALL_VIEW_EVENTS:
                stages["paywall_view"] += 1
            if event.event_name in PAYWALL_CTA_EVENTS:
                stages["paywall_click"] += 1
            if event.event_name in PAYMENT_EVENTS:
                stages["payment_success"] += 1

        stage_keys = ["active_users", "paywall_view", "paywall_click", "payment_success"]
        stage_objects: List[FunnelStage] = []
        previous = None
        for key in stage_keys:
            value = stages[key]
            conversion = value / previous * 100 if previous else None
            stage_objects.append(FunnelStage(label=key.replace("_", " ").title(), count=value, conversion_rate=conversion))
            previous = value if value else previous
        return FunnelBreakdown(name="Membership Funnel", stages=stage_objects)

    def _learning_funnel(self, filters: DashboardFilters, windows: _TimeWindows) -> FunnelBreakdown:
        stage_sets = {
            "active_users": set(),
            "learning_users": set(),
            "completed_users": set(),
            "streak_users": set(),
        }
        for event, _ in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if not event.user_id:
                continue
            if event.event_name in ENGAGEMENT_EVENTS:
                stage_sets["active_users"].add(event.user_id)
            if event.event_name in {"lesson_started", "practice_started"}:
                stage_sets["learning_users"].add(event.user_id)
            if event.event_name in {"lesson_completed", "practice_done"}:
                stage_sets["completed_users"].add(event.user_id)
            if event.properties.get("streak_days", 0) >= 3:
                stage_sets["streak_users"].add(event.user_id)

        ordered = ["active_users", "learning_users", "completed_users", "streak_users"]
        stage_objects: List[FunnelStage] = []
        previous = None
        for key in ordered:
            value = len(stage_sets[key])
            conversion = value / previous * 100 if previous else None
            stage_objects.append(FunnelStage(label=key.replace("_", " ").title(), count=value, conversion_rate=conversion))
            previous = value if value else previous
        return FunnelBreakdown(name="Learning Funnel", stages=stage_objects)

    def _build_growth(self, filters: DashboardFilters, windows: _TimeWindows) -> DashboardSection:
        new_user_series = self._daily_event_series(filters, windows, {"user_registered"}, "New Users")
        new_member_series = self._daily_event_series(filters, windows, PAYMENT_EVENTS, "New Members")

        cards = [
            _build_card(
                "new_users_range",
                "New Users (range)",
                sum(point.value for point in new_user_series.points),
            )
        ]
        segment_series = self._daily_active_users_by_segment(filters, windows)
        trends = [
            new_user_series,
            new_member_series,
            *segment_series,
            self._retention_heatmap(filters, windows),
        ]
        tables = {"channels": self._top_channels(filters, windows)}
        return DashboardSection(cards=cards, trends=trends, tables=tables)

    def _daily_active_users_by_segment(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[TrendSeries]:
        segments = ("new", "returning", "resurrected")
        per_segment: Dict[str, List[TrendPoint]] = {segment: [] for segment in segments}

        for day in _daterange(windows.current_start, windows.current_end):
            next_day = day + timedelta(days=1)
            counts = {segment: 0 for segment in segments}
            for event, _ in self.dataset.iter_events(filters, start=day, end=next_day):
                if not event.user_id:
                    continue
                segment = event.properties.get("user_segment")
                if segment not in segments:
                    if event.properties.get("is_new_user"):
                        segment = "new"
                    elif event.properties.get("was_dormant"):
                        segment = "resurrected"
                    else:
                        segment = "returning"
                counts[segment] += 1
            for segment in segments:
                per_segment[segment].append(TrendPoint(timestamp=day, value=counts[segment]))

        return [
            TrendSeries(name=f"Active Users ({segment})", points=points, unit="users")
            for segment, points in per_segment.items()
        ]

    def _retention_heatmap(self, filters: DashboardFilters, windows: _TimeWindows) -> TrendSeries:
        points: List[TrendPoint] = []
        cohorts: Dict[datetime, List[str]] = defaultdict(list)
        for event, localized_time in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if event.event_name not in {"user_registered", "new_user"} or not event.user_id:
                continue
            cohort_day = localized_time.replace(hour=0, minute=0, second=0, microsecond=0)
            cohorts[cohort_day].append(event.user_id)

        for cohort_day, users in cohorts.items():
            base = len(users)
            if not base:
                continue
            for offset in filters.retention_days:
                day_start = cohort_day + timedelta(days=offset)
                day_end = day_start + timedelta(days=1)
                active = 0
                for event, _ in self.dataset.iter_events(filters, start=day_start, end=day_end):
                    if event.user_id in users:
                        active += 1
                retention = active / base * 100
                points.append(TrendPoint(timestamp=day_start, value=retention))

        return TrendSeries(name="Retention Heatmap", points=points, unit="%")

    def _build_monetization(self, filters: DashboardFilters, windows: _TimeWindows) -> DashboardSection:
        trends = [self._ltv_curve(filters, windows)]
        tables = {"plans": self._plan_breakdown(filters, windows)}
        funnels = [self._membership_funnel(filters, windows)]
        return DashboardSection(cards=[], trends=trends, tables=tables, funnels=funnels)

    def _ltv_curve(self, filters: DashboardFilters, windows: _TimeWindows) -> TrendSeries:
        points: List[TrendPoint] = []
        cumulative = 0.0
        for day in _daterange(windows.current_start, windows.current_end):
            day_end = day + timedelta(days=1)
            revenue = sum(membership.amount for membership in self.dataset.memberships_between(day, day_end))
            cumulative += revenue
            points.append(TrendPoint(timestamp=day, value=cumulative))
        return TrendSeries(name="LTV Curve", points=points, unit="$")

    def _plan_breakdown(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[LeaderboardRow]:
        plans = Counter(
            membership.plan_type for membership in self.dataset.memberships_between(windows.current_start, windows.current_end)
        )
        total = sum(plans.values()) or 1
        return [
            LeaderboardRow(label=plan, metrics={"count": count, "share": count / total * 100})
            for plan, count in sorted(plans.items(), key=lambda item: item[1], reverse=True)
        ]

    def _build_learning(self, filters: DashboardFilters, windows: _TimeWindows) -> DashboardSection:
        completion_trend = self._learning_completion_trend(filters, windows)
        cards = [
            _build_card(
                "learning_completion_rate",
                "Learning Completion Rate",
                completion_trend.points[-1].value if completion_trend.points else 0,
                unit="%",
            )
        ]
        trends = [completion_trend]
        tables = {
            "courses": self._top_courses(filters, windows),
            "words": self._top_words(filters, windows),
        }
        funnels = [self._learning_funnel(filters, windows)]
        return DashboardSection(cards=cards, trends=trends, tables=tables, funnels=funnels)

    def _build_ops(self, filters: DashboardFilters, windows: _TimeWindows) -> DashboardSection:
        cards = self._ops_cards(filters, windows)
        trends = [self._latency_trend(filters, windows)]
        tables = {"model_usage": self._model_usage_table(filters, windows)}
        return DashboardSection(cards=cards, trends=trends, tables=tables)

    def _ops_cards(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[CardMetric]:
        success, total, cost = 0, 0, 0.0
        for event, _ in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if event.event_name not in SYSTEM_EVENTS:
                continue
            total += 1
            if event.properties.get("success") or str(event.properties.get("status")).startswith("2"):
                success += 1
            cost += float(event.properties.get("cost") or 0.0)

        success_rate = success / total * 100 if total else 0.0
        avg_cost = cost / total if total else 0.0
        return [
            CardMetric(key="system_success", label="System Success Rate", value=success_rate, unit="%"),
            CardMetric(key="system_cost", label="Avg Generation Cost", value=avg_cost, unit="$"),
        ]

    def _latency_trend(self, filters: DashboardFilters, windows: _TimeWindows) -> TrendSeries:
        points: List[TrendPoint] = []
        for day in _daterange(windows.current_start, windows.current_end):
            latencies: List[float] = []
            for event, _ in self.dataset.iter_events(filters, start=day, end=day + timedelta(days=1)):
                if event.event_name not in SYSTEM_EVENTS:
                    continue
                latencies.append(float(event.properties.get("latency_ms") or 0.0))
            avg_latency = mean(latencies) if latencies else 0.0
            points.append(TrendPoint(timestamp=day, value=avg_latency))
        return TrendSeries(name="Latency", points=points, unit="ms")

    def _model_usage_table(self, filters: DashboardFilters, windows: _TimeWindows) -> Sequence[LeaderboardRow]:
        usage: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "tokens": 0})
        for event, _ in self.dataset.iter_events(filters, start=windows.current_start, end=windows.current_end):
            if event.event_name not in SYSTEM_EVENTS:
                continue
            model = str(event.properties.get("model") or "unknown")
            usage[model]["count"] += 1
            usage[model]["tokens"] += float(event.properties.get("tokens") or 0.0)
        return [
            LeaderboardRow(label=model, metrics=metrics)
            for model, metrics in sorted(usage.items(), key=lambda item: item[1]["count"], reverse=True)
        ]

    def _calculate_renewal_rates(self, filters: DashboardFilters, windows: _TimeWindows) -> Tuple[float, float]:
        lookahead = timedelta(days=filters.comparison_days)
        current_renewals, current_expiring = 0, 0
        previous_renewals, previous_expiring = 0, 0
        for membership in self.dataset.memberships:
            if windows.primary_day_start <= membership.expire_at < windows.primary_day_end + lookahead:
                current_expiring += 1
                if self._has_follow_up_membership(membership.user_id, membership.expire_at):
                    current_renewals += 1
            elif windows.previous_day_start <= membership.expire_at < windows.previous_day_end + lookahead:
                previous_expiring += 1
                if self._has_follow_up_membership(membership.user_id, membership.expire_at):
                    previous_renewals += 1

        current_rate = current_renewals / current_expiring * 100 if current_expiring else 0.0
        previous_rate = previous_renewals / previous_expiring * 100 if previous_expiring else 0.0
        return current_rate, previous_rate

    def _has_follow_up_membership(self, user_id: str, after: datetime) -> bool:
        for membership in self.dataset.memberships:
            if membership.user_id != user_id:
                continue
            if membership.start_at > after and membership.status == "active":
                return True
        return False

    def _calculate_revenue_metrics(
        self, filters: DashboardFilters, windows: _TimeWindows
    ) -> Tuple[float, float, float, float]:
        def _sum_revenue(start: datetime, end: datetime) -> Tuple[float, int]:
            records = self.dataset.memberships_between(start, end)
            return sum(record.amount for record in records), len({record.user_id for record in records})

        revenue, payers = _sum_revenue(windows.primary_day_start, windows.primary_day_end)
        previous_revenue, previous_payers = _sum_revenue(windows.previous_day_start, windows.previous_day_end)
        dau = self.dataset.unique_users(filters, start=windows.primary_day_start, end=windows.primary_day_end) or 1
        dau_prev = self.dataset.unique_users(filters, start=windows.previous_day_start, end=windows.previous_day_end) or 1
        arpu = revenue / dau
        arppu = revenue / payers if payers else 0.0
        arpu_prev = previous_revenue / dau_prev
        arppu_prev = previous_revenue / previous_payers if previous_payers else 0.0
        return arpu, arpu_prev, arppu, arppu_prev

    def _calculate_study_minutes(self, filters: DashboardFilters, windows: _TimeWindows) -> Tuple[float, float]:
        def _calc(start: datetime, end: datetime) -> float:
            total_seconds = 0.0
            users = set()
            for event, _ in self.dataset.iter_events(filters, start=start, end=end):
                if event.event_name not in {"study_session", "lesson_completed"}:
                    continue
                total_seconds += float(event.properties.get("duration_seconds") or 0.0)
                if event.user_id:
                    users.add(event.user_id)
            return (total_seconds / 60) / len(users) if users else 0.0

        return _calc(windows.primary_day_start, windows.primary_day_end), _calc(
            windows.previous_day_start, windows.previous_day_end
        )

    def _calculate_practice_count(self, filters: DashboardFilters, windows: _TimeWindows) -> Tuple[float, float]:
        def _calc(start: datetime, end: datetime) -> float:
            attempts = 0
            users = set()
            for event, _ in self.dataset.iter_events(filters, start=start, end=end):
                if event.event_name != "practice_done":
                    continue
                attempts += 1
                if event.user_id:
                    users.add(event.user_id)
            return attempts / len(users) if users else 0.0

        return _calc(windows.primary_day_start, windows.primary_day_end), _calc(
            windows.previous_day_start, windows.previous_day_end
        )

    def _calculate_retention(self, filters: DashboardFilters, day_offset: int, windows: _TimeWindows) -> Tuple[float, float]:
        def _calc(window_start: datetime, window_end: datetime) -> float:
            cohort_users = [
                event.user_id
                for event, _ in self.dataset.iter_events(filters, start=window_start, end=window_end)
                if event.event_name in {"user_registered", "new_user"} and event.user_id
            ]
            if not cohort_users:
                return 0.0
            retained = 0
            follow_up_start = window_start + timedelta(days=day_offset)
            follow_up_end = follow_up_start + timedelta(days=1)
            for user_id in cohort_users:
                for event, _ in self.dataset.iter_events(filters, start=follow_up_start, end=follow_up_end):
                    if event.user_id == user_id:
                        retained += 1
                        break
            return retained / len(cohort_users) * 100

        return _calc(windows.primary_day_start, windows.primary_day_end), _calc(
            windows.previous_day_start, windows.previous_day_end
        )
