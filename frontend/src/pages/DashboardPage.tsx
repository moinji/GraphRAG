import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getHealth, getLLMUsage, getQueryAnalytics, getQueryHistory, fetchGraphStats } from '@/api/client';

interface DashboardPageProps {
  onBack: () => void;
}

interface HealthData {
  status: string;
  neo4j: { status: string; latency_ms?: number };
  postgres: { status: string; latency_ms?: number };
  llm: { status: string; detail?: string };
}

interface Analytics {
  total_queries: number;
  cache_hit_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  error_count: number;
  error_rate: number;
  by_mode: Record<string, number>;
  by_route: Record<string, number>;
}

interface LLMUsage {
  total_calls: number;
  total_tokens: number;
  estimated_total_cost_usd: number;
  by_caller: Record<string, { call_count: number; estimated_cost_usd: number }>;
}

interface GStats {
  total_nodes: number;
  total_edges: number;
  node_types: Record<string, number>;
  edge_types: Record<string, number>;
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === 'ok' || status === 'healthy'
      ? 'bg-green-100 text-green-800'
      : status === 'degraded'
        ? 'bg-yellow-100 text-yellow-800'
        : 'bg-red-100 text-red-800';
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${color}`}>{status}</span>;
}

export default function DashboardPage({ onBack }: DashboardPageProps) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [llmUsage, setLlmUsage] = useState<LLMUsage | null>(null);
  const [graphStats, setGraphStats] = useState<GStats | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [h, a, l, g, hist] = await Promise.allSettled([
        getHealth(),
        getQueryAnalytics(),
        getLLMUsage(),
        fetchGraphStats(),
        getQueryHistory(10),
      ]);
      if (h.status === 'fulfilled') setHealth(h.value as unknown as HealthData);
      if (a.status === 'fulfilled') setAnalytics(a.value as unknown as Analytics);
      if (l.status === 'fulfilled') setLlmUsage(l.value as unknown as LLMUsage);
      if (g.status === 'fulfilled') setGraphStats(g.value as unknown as GStats);
      if (hist.status === 'fulfilled') setHistory(((hist.value as unknown as { history: Record<string, unknown>[] }).history) ?? []);
      setLoading(false);
    }
    load();
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Button variant="outline" onClick={onBack}>
          돌아가기
        </Button>
      </div>

      {loading && <p className="text-muted-foreground">로딩 중...</p>}

      {/* Service Health */}
      {health && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              서비스 상태 <StatusBadge status={health.status} />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">Neo4j</p>
                <StatusBadge status={health.neo4j.status} />
                {health.neo4j.latency_ms != null && (
                  <p className="mt-1 text-xs text-muted-foreground">{health.neo4j.latency_ms}ms</p>
                )}
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">PostgreSQL</p>
                <StatusBadge status={health.postgres.status} />
                {health.postgres.latency_ms != null && (
                  <p className="mt-1 text-xs text-muted-foreground">{health.postgres.latency_ms}ms</p>
                )}
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">LLM</p>
                <StatusBadge status={health.llm.status} />
                {health.llm.detail && (
                  <p className="mt-1 text-xs text-muted-foreground truncate" title={health.llm.detail}>
                    {health.llm.detail}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-xs text-muted-foreground">총 쿼리</p>
            <p className="text-2xl font-bold">{analytics?.total_queries ?? '-'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-xs text-muted-foreground">캐시 히트율</p>
            <p className="text-2xl font-bold">
              {analytics ? `${(analytics.cache_hit_rate * 100).toFixed(1)}%` : '-'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-xs text-muted-foreground">평균 레이턴시</p>
            <p className="text-2xl font-bold">
              {analytics?.avg_latency_ms ? `${analytics.avg_latency_ms}ms` : '-'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-xs text-muted-foreground">p95 레이턴시</p>
            <p className="text-2xl font-bold">
              {analytics?.p95_latency_ms ? `${analytics.p95_latency_ms}ms` : '-'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Graph Stats + LLM Cost */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {graphStats && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Knowledge Graph</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-xs text-muted-foreground">노드</p>
                  <p className="text-lg font-bold">{graphStats.total_nodes}</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-xs text-muted-foreground">관계</p>
                  <p className="text-lg font-bold">{graphStats.total_edges}</p>
                </div>
              </div>
              {Object.keys(graphStats.node_types).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {Object.entries(graphStats.node_types).map(([type, count]) => (
                    <span key={type} className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                      {type}: {count}
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {llmUsage && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">LLM 사용량</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-xs text-muted-foreground">API 호출</p>
                  <p className="text-lg font-bold">{llmUsage.total_calls}</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-xs text-muted-foreground">총 토큰</p>
                  <p className="text-lg font-bold">{llmUsage.total_tokens.toLocaleString()}</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-xs text-muted-foreground">비용 (USD)</p>
                  <p className="text-lg font-bold">${llmUsage.estimated_total_cost_usd.toFixed(4)}</p>
                </div>
              </div>
              {Object.keys(llmUsage.by_caller).length > 0 && (
                <div className="mt-3 space-y-1">
                  {Object.entries(llmUsage.by_caller).map(([caller, data]) => (
                    <div key={caller} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{caller}</span>
                      <span>{data.call_count}회 (${data.estimated_cost_usd.toFixed(4)})</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Query Mode Distribution */}
      {analytics && Object.keys(analytics.by_mode).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">쿼리 모드 분포</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4">
              {Object.entries(analytics.by_mode).map(([mode, count]) => (
                <div key={mode} className="flex items-center gap-2">
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                      mode === 'a'
                        ? 'bg-blue-100 text-blue-800'
                        : mode === 'b'
                          ? 'bg-orange-100 text-orange-800'
                          : 'bg-purple-100 text-purple-800'
                    }`}
                  >
                    Mode {mode.toUpperCase()}
                  </span>
                  <span className="text-sm font-medium">{count}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Query History */}
      {history.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">최근 쿼리</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {history.map((q, i) => (
                <div key={i} className="flex items-center gap-2 text-sm border-b pb-2 last:border-0">
                  <span
                    className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                      q.mode === 'a'
                        ? 'bg-blue-50 text-blue-700'
                        : q.mode === 'b'
                          ? 'bg-orange-50 text-orange-700'
                          : 'bg-purple-50 text-purple-700'
                    }`}
                  >
                    {String(q.mode).toUpperCase()}
                  </span>
                  <span className="flex-1 truncate">{String(q.question)}</span>
                  {Boolean(q.cached) && <span className="rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700">cached</span>}
                  {q.latency_ms != null && (
                    <span className="text-xs text-muted-foreground">{String(q.latency_ms)}ms</span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
