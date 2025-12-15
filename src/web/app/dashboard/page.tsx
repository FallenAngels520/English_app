'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import type {
  CardMetric,
  DashboardApiResponse,
  DashboardRequestPayload,
  DashboardResult,
  DashboardSection,
  EventPayload,
  FunnelBreakdown,
  MembershipPayload,
  TrendSeries
} from '@/types/dashboard';

const API_BASE = (process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const DASHBOARD_ENDPOINT = `${API_BASE}/dashboard/dashboard`;

type RangeOption = { label: string; value: number };

const RANGE_OPTIONS: RangeOption[] = [
  { label: '近7天', value: 7 },
  { label: '近30天', value: 30 },
  { label: '近90天', value: 90 }
];

export default function DashboardPage() {
  const [range, setRange] = useState<RangeOption>(RANGE_OPTIONS[0]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DashboardResult | null>(null);
  const [source, setSource] = useState<string | null>(null);

  const fetchDashboard = useCallback(async (rangeValue: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - rangeValue);

    const basePayload: DashboardRequestPayload = {
      start: start.toISOString(),
      end: end.toISOString(),
      timezone: 'Europe/Berlin'
    };

    const initial = await postDashboard(basePayload);
    if (initial.ok) {
      return (await initial.json()) as DashboardApiResponse;
    }
    const detail = await initial.text().catch(() => '');
    if (!detail.toLowerCase().includes('data_dashboard_database_url')) {
      throw new Error(detail || '无法加载数据看板');
    }

    const sample = generateSampleDataset(start, end);
    const inlinePayload: DashboardRequestPayload = {
      ...basePayload,
      events: sample.events,
      memberships: sample.memberships
    };
    const inlineResponse = await postDashboard(inlinePayload);
    if (!inlineResponse.ok) {
      const inlineDetail = await inlineResponse.text().catch(() => '');
      throw new Error(inlineDetail || '无法加载数据看板');
    }
    return (await inlineResponse.json()) as DashboardApiResponse;
  }, []);

  const refresh = useCallback(
    async (rangeValue: number) => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchDashboard(rangeValue);
        setData(response.data);
        setSource(response.source);
      } catch (fetchError) {
        setError((fetchError as Error).message || '加载失败');
      } finally {
        setLoading(false);
      }
    },
    [fetchDashboard]
  );

  useEffect(() => {
    refresh(range.value).catch(() => {});
  }, [range, refresh]);

  const sections = useMemo(() => {
    if (!data) return [];
    return [
      { key: 'executive', title: '总览', description: '核心KPI与趋势', section: data.executive },
      { key: 'growth', title: '用户增长', description: '新增、活跃、渠道质量', section: data.growth },
      { key: 'monetization', title: '会员与收入', description: '漏斗、订阅结构、LTV', section: data.monetization },
      { key: 'learning', title: '学习与内容', description: '完成率、词书表现与生成内容反馈', section: data.learning },
      { key: 'ops', title: '系统与成本', description: '模型成功率、耗时与成本', section: data.ops }
    ];
  }, [data]);

  return (
    <div className="min-h-screen bg-muted/20">
      <header className="sticky top-0 z-10 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-6 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">Dashboard</p>
            <h1 className="text-2xl font-semibold">数据看板</h1>
            <p className="text-sm text-muted-foreground">
              数据源：{source ?? '加载中'} · 当前范围：{range.label}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex gap-1 rounded-full border border-border/60 bg-card/60 p-1">
              {RANGE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`rounded-full px-3 py-1 text-sm transition ${
                    option.value === range.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                  }`}
                  onClick={() => setRange(option)}
                  disabled={loading}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <Button variant="secondary" onClick={() => refresh(range.value)} disabled={loading}>
              刷新
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-8">
        {error && (
          <Alert variant="destructive">
            <AlertTitle>加载失败</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {loading && (
          <div className="rounded-2xl border border-dashed border-border/60 bg-card/60 px-4 py-6 text-center text-sm text-muted-foreground">
            正在加载数据...
          </div>
        )}

        {!loading && !data && !error && (
          <div className="rounded-2xl border border-dashed border-border/60 bg-card/60 px-4 py-6 text-center text-sm text-muted-foreground">
            暂无数据，请检查后端数据源或时间范围。
          </div>
        )}

        {data &&
          sections.map(({ key, title, description, section }) => (
            <section key={key} className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">{key}</p>
                  <h2 className="text-xl font-semibold">{title}</h2>
                </div>
                <p className="text-sm text-muted-foreground">{description}</p>
              </div>
              <MetricGrid cards={section.cards} />
              <TrendGrid trends={section.trends} />
              <TableGrid tables={section.tables} />
              <FunnelGrid funnels={section.funnels ?? []} />
            </section>
          ))}
      </main>
    </div>
  );
}

function MetricGrid({ cards }: { cards: CardMetric[] }) {
  if (!cards?.length) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => {
        const formattedValue = formatMetricValue(card.value, card.unit);
        const delta = card.deltaPercent ?? null;
        return (
          <div key={card.key} className="rounded-2xl border border-border/60 bg-card/80 p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{translateCardLabel(card.label)}</p>
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-semibold">{formattedValue}</p>
              {delta != null && (
                <span className={`text-sm ${delta >= 0 ? 'text-emerald-600' : 'text-destructive'}`}>
                  {delta >= 0 ? '+' : ''}
                  {delta.toFixed(1)}%
                </span>
              )}
            </div>
            {card.description && <p className="mt-1 text-xs text-muted-foreground">{card.description}</p>}
          </div>
        );
      })}
    </div>
  );
}

function TrendGrid({ trends }: { trends: TrendSeries[] }) {
  if (!trends?.length) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {trends.map((series) => (
        <TrendCard key={series.name} series={series} />
      ))}
    </div>
  );
}

function TrendCard({ series }: { series: TrendSeries }) {
  const points = series.points || [];
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  const maxValue = Math.max(...points.map((point) => point.value), 1);

  return (
    <div className="rounded-2xl border border-border/60 bg-card/80 p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{series.name}</p>
          <p className="text-2xl font-semibold">{latest ? formatMetricValue(latest.value, series.unit) : '——'}</p>
        </div>
        {latest && previous && (
          <p className={`text-sm ${latest.value - previous.value >= 0 ? 'text-emerald-600' : 'text-destructive'}`}>
            {(latest.value - previous.value >= 0 ? '+' : '') + (latest.value - previous.value).toFixed(1)} vs 上期
          </p>
        )}
      </div>
      <div className="mt-4 flex h-24 items-end gap-1">
        {points.slice(-24).map((point) => {
          const height = (point.value / maxValue) * 100;
          return (
            <span
              key={point.timestamp}
              className="flex-1 rounded bg-primary/50"
              style={{ height: `${height}%` }}
              title={`${new Date(point.timestamp).toLocaleDateString()} · ${point.value.toFixed(2)}${series.unit ?? ''}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function TableGrid({ tables }: { tables: DashboardSection['tables'] }) {
  const entries = Object.entries(tables ?? {});
  if (!entries.length) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {entries.map(([title, rows]) => (
        <div key={title} className="rounded-2xl border border-border/60 bg-card/80 p-5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">{translateTableTitle(title)}</p>
            <span className="text-xs text-muted-foreground">Top {rows.length}</span>
          </div>
          <div className="mt-3 divide-y divide-border/60 text-sm">
            {rows.map((row) => (
              <div key={row.label} className="flex items-center justify-between py-2">
                <span className="font-medium text-foreground">{row.label}</span>
                <div className="text-right text-xs text-muted-foreground">
                  {Object.entries(row.metrics).map(([metricKey, value]) => (
                    <div key={metricKey}>
                      {translateMetricKey(metricKey)}：{value.toFixed(1)}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FunnelGrid({ funnels }: { funnels: FunnelBreakdown[] }) {
  if (!funnels.length) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {funnels.map((funnel) => (
        <div key={funnel.name} className="rounded-2xl border border-border/60 bg-card/80 p-5">
          <p className="text-sm font-semibold">{funnel.name}</p>
          <div className="mt-4 space-y-3">
            {funnel.stages.map((stage, index) => (
              <div key={stage.label} className="rounded-xl bg-muted/40 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold">{stage.label}</p>
                    <p className="text-xs text-muted-foreground">人数：{stage.count}</p>
                  </div>
                  {stage.conversionRate != null && (
                    <span className="text-xs text-muted-foreground">转化率：{stage.conversionRate.toFixed(1)}%</span>
                  )}
                </div>
                {index < funnel.stages.length - 1 && <div className="mt-3 h-1 rounded-full bg-gradient-to-r from-primary/40 to-transparent" />}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function formatMetricValue(value: number, unit?: string | null) {
  if (Math.abs(value) >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M${unit ?? ''}`;
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)}K${unit ?? ''}`;
  }
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2)}${unit ?? ''}`;
}

function translateTableTitle(title: string) {
  switch (title) {
    case 'top_courses':
      return 'Top 课程';
    case 'top_words':
      return 'Top 单词';
    case 'top_channels':
      return 'Top 渠道';
    case 'plans':
      return '订阅结构';
    default:
      return title;
  }
}

function translateCardLabel(label: string) {
  const mapping: Record<string, string> = {
    DAU: 'DAU（日活）',
    WAU: 'WAU（周活）',
    MAU: 'MAU（月活）',
    'New Users': 'New Users（新增用户）',
    'Active Members': 'Active Members（在期会员）',
    'New Members': 'New Members（新增会员）',
    'Member Conversion Rate': '会员转化率',
    'Renewal Rate': '续费率',
    ARPU: 'ARPU（人均收入）',
    ARPPU: 'ARPPU（付费用户ARPU）',
    'Avg Study Minutes': '人均学习时长',
    'Avg Practice Count': '人均练习次数',
    'D1 Retention': 'D1 留存'
  };
  return mapping[label] ?? label;
}

function translateMetricKey(key: string) {
  const mapping: Record<string, string> = {
    completions: '完成数',
    completion_rate: '完成率',
    avg_minutes: '平均时长',
    practice_count: '练习次数',
    error_rate: '错误率',
    mastery_rate: '掌握率',
    new_users: '新增用户',
    count: '人数',
    share: '占比',
    tokens: 'Tokens',
    model: '模型'
  };
  return mapping[key] ?? key;
}

async function postDashboard(payload: DashboardRequestPayload) {
  return fetch(DASHBOARD_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

function generateSampleDataset(start: Date, end: Date): { events: EventPayload[]; memberships: MembershipPayload[] } {
  const events: EventPayload[] = [];
  const memberships: MembershipPayload[] = [];
  const dayMs = 86_400_000;
  const days = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / dayMs));
  const channels = ['organic', 'campaign', 'referral'];
  const platforms = ['ios', 'android', 'web'];
  const regions = ['CN', 'US', 'DE'];
  const locales = ['zh-CN', 'en-US', 'de-DE'];
  const courses = ['starter', 'travel', 'business'];
  const words = ['oasis', 'momentum', 'pioneer', 'nostalgia'];
  const models = ['gpt-4o-mini', 'qwen-plus', 'tts-pro'];

  for (let dayIndex = 0; dayIndex < days; dayIndex++) {
    const day = new Date(start.getTime() + dayIndex * dayMs);
    const iso = (hours: number) => new Date(day.getTime() + hours * 3600000).toISOString();
    for (let userIndex = 0; userIndex < 6; userIndex++) {
      const userId = `user-${dayIndex}-${userIndex}`;
      const channel = channels[(dayIndex + userIndex) % channels.length];
      const platform = platforms[(dayIndex + userIndex) % platforms.length];
      const region = regions[(dayIndex + userIndex) % regions.length];
      const locale = locales[(dayIndex + userIndex) % locales.length];
      const courseId = courses[(dayIndex + userIndex) % courses.length];
      const wordId = words[(dayIndex + userIndex) % words.length];
      const appVersion = `1.${5 + ((dayIndex + userIndex) % 3)}.${(dayIndex + userIndex) % 10}`;

      events.push(
        createEvent(`reg-${dayIndex}-${userIndex}`, userId, 'user_registered', iso(1 + userIndex * 0.2), {
          channel,
          platform,
          region,
          locale,
          app_version: appVersion,
          user_segment: 'new',
          is_new_user: true
        })
      );
      events.push(
        createEvent(`app-${dayIndex}-${userIndex}`, userId, 'app_open', iso(2 + userIndex * 0.2), {
          channel,
          platform,
          region,
          locale,
          app_version: appVersion,
          user_segment: dayIndex > 0 ? 'returning' : 'new'
        })
      );
      events.push(
        createEvent(`lesson-start-${dayIndex}-${userIndex}`, userId, 'lesson_started', iso(3 + userIndex * 0.2), {
          course_id: courseId,
          channel,
          platform,
          region,
          locale
        })
      );
      events.push(
        createEvent(`lesson-complete-${dayIndex}-${userIndex}`, userId, 'lesson_completed', iso(3.5 + userIndex * 0.2), {
          course_id: courseId,
          duration_seconds: 420 + dayIndex * 5,
          channel,
          platform,
          region,
          locale
        })
      );
      events.push(
        createEvent(`practice-${dayIndex}-${userIndex}`, userId, 'practice_done', iso(4 + userIndex * 0.2), {
          word_id: wordId,
          correct: (userIndex + dayIndex) % 3 !== 0,
          channel,
          platform,
          region,
          locale,
          streak_days: (dayIndex % 5) + 1
        })
      );
      events.push(
        createEvent(`study-${dayIndex}-${userIndex}`, userId, 'study_session', iso(4.5 + userIndex * 0.2), {
          duration_seconds: 900 + userIndex * 30,
          channel,
          platform
        })
      );

      if (userIndex % 2 === 0) {
        events.push(createEvent(`payview-${dayIndex}-${userIndex}`, userId, 'subscribe_view', iso(5 + userIndex * 0.1), { channel, platform }));
        events.push(
          createEvent(`payclick-${dayIndex}-${userIndex}`, userId, 'paywall_cta_click', iso(5.2 + userIndex * 0.1), {
            channel,
            platform
          })
        );
        events.push(createEvent(`paysuccess-${dayIndex}-${userIndex}`, userId, 'pay_success', iso(5.5 + userIndex * 0.1), { channel, platform }));

        const planType = userIndex % 3 === 0 ? 'yearly' : 'monthly';
        const startAt = new Date(day.getTime() + 6 * 3600000 + userIndex * 60000);
        const expireAt = new Date(startAt);
        expireAt.setDate(expireAt.getDate() + (planType === 'yearly' ? 365 : 30));
        memberships.push(
          createMembership(userId, planType, startAt.toISOString(), expireAt.toISOString(), planType === 'yearly' ? 188 : 28)
        );
      }

      const modelName = models[(dayIndex + userIndex) % models.length];
      events.push(
        createEvent(`model-${dayIndex}-${userIndex}`, userId, 'model_invoke', iso(6 + userIndex * 0.1), {
          model: modelName,
          latency_ms: 400 + (dayIndex % 5) * 30,
          success: true,
          status: 200,
          tokens: 1200 + dayIndex * 40,
          cost: 0.02 * (1 + dayIndex / 10)
        })
      );
      events.push(
        createEvent(`image-${dayIndex}-${userIndex}`, userId, 'image_generation', iso(6.5 + userIndex * 0.1), {
          model: 'image-pro',
          latency_ms: 950 + dayIndex * 15,
          success: true,
          cost: 0.05
        })
      );
      events.push(
        createEvent(`tts-${dayIndex}-${userIndex}`, userId, 'tts_generation', iso(6.7 + userIndex * 0.1), {
          model: 'tts-pro',
          latency_ms: 320 + dayIndex * 10,
          success: true,
          cost: 0.01
        })
      );
    }
  }

  return { events, memberships };
}

function createEvent(
  id: string,
  userId: string,
  name: string,
  timestamp: string,
  properties: Record<string, unknown>
): EventPayload {
  return {
    id,
    user_id: userId,
    event_name: name,
    event_time: timestamp,
    properties
  };
}

function createMembership(userId: string, planType: string, startAt: string, expireAt: string, amount: number): MembershipPayload {
  return {
    user_id: userId,
    plan_type: planType,
    start_at: startAt,
    expire_at: expireAt,
    status: 'active',
    amount,
    order_id: `${userId}-${planType}`
  };
}
