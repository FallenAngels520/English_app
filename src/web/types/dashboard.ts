export interface CardMetric {
  key: string;
  label: string;
  value: number;
  unit?: string | null;
  deltaPercent?: number | null;
  description?: string | null;
}

export interface TrendPoint {
  timestamp: string;
  value: number;
}

export interface TrendSeries {
  name: string;
  unit?: string | null;
  points: TrendPoint[];
  comparisonPoints?: TrendPoint[] | null;
}

export interface FunnelStage {
  label: string;
  count: number;
  conversionRate?: number | null;
}

export interface FunnelBreakdown {
  name: string;
  stages: FunnelStage[];
}

export interface LeaderboardRow {
  label: string;
  metrics: Record<string, number>;
}

export interface DashboardSection {
  cards: CardMetric[];
  trends: TrendSeries[];
  tables: Record<string, LeaderboardRow[]>;
  funnels?: FunnelBreakdown[];
}

export interface DashboardResult {
  executive: DashboardSection;
  growth: DashboardSection;
  monetization: DashboardSection;
  learning: DashboardSection;
  ops: DashboardSection;
}

export interface DashboardApiResponse {
  data: DashboardResult;
  source: string;
}

export interface EventPayload {
  id: string;
  user_id?: string | null;
  event_name: string;
  event_time: string;
  properties: Record<string, unknown>;
}

export interface MembershipPayload {
  user_id: string;
  plan_type: string;
  start_at: string;
  expire_at: string;
  status: string;
  amount: number;
  order_id?: string | null;
}

export interface DashboardRequestPayload {
  start: string;
  end: string;
  timezone: string;
  channel?: string | null;
  region?: string | null;
  locale?: string | null;
  platform?: string | null;
  app_version?: string | null;
  events?: EventPayload[];
  memberships?: MembershipPayload[];
}
