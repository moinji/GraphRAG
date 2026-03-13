import { Badge } from '@/components/ui/badge';
import { getNodeColor } from './graph-styles';
import type { GraphStats } from '@/types/graph';

interface KGStatsDashboardProps {
  stats: GraphStats;
  visible: boolean;
  onToggle: () => void;
}

export default function KGStatsDashboard({ stats, visible, onToggle }: KGStatsDashboardProps) {
  if (!visible) {
    return (
      <button
        onClick={onToggle}
        className="absolute bottom-3 left-3 z-10 rounded-lg border bg-background/90 px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur hover:bg-accent"
      >
        통계 보기
      </button>
    );
  }

  const topNodes = Object.entries(stats.node_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  const topEdges = Object.entries(stats.edge_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  const nodeTypeCount = Object.keys(stats.node_counts).length;
  const edgeTypeCount = Object.keys(stats.edge_counts).length;

  // Simple density = edges / nodes (graph connectivity measure)
  const density = stats.total_nodes > 0
    ? (stats.total_edges / stats.total_nodes).toFixed(2)
    : '0';

  return (
    <div className="absolute bottom-3 left-3 z-10 w-72 rounded-lg border bg-background/95 shadow-lg backdrop-blur">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">KG 통계</h4>
        <button
          onClick={onToggle}
          className="text-muted-foreground hover:text-foreground text-lg leading-none"
        >
          &times;
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-2 p-3">
        <div className="rounded-md border p-2 text-center">
          <p className="text-lg font-bold">{stats.total_nodes.toLocaleString()}</p>
          <p className="text-[10px] text-muted-foreground">노드</p>
        </div>
        <div className="rounded-md border p-2 text-center">
          <p className="text-lg font-bold">{stats.total_edges.toLocaleString()}</p>
          <p className="text-[10px] text-muted-foreground">엣지</p>
        </div>
        <div className="rounded-md border p-2 text-center">
          <p className="text-lg font-bold">{density}</p>
          <p className="text-[10px] text-muted-foreground">밀도</p>
        </div>
      </div>

      {/* Type summary */}
      <div className="flex gap-3 border-t px-3 py-2 text-xs text-muted-foreground">
        <span>{nodeTypeCount}개 노드 타입</span>
        <span>{edgeTypeCount}개 엣지 타입</span>
      </div>

      {/* Node type distribution */}
      <div className="border-t px-3 py-2">
        <h5 className="text-[10px] font-semibold uppercase text-muted-foreground mb-1.5">
          노드 타입 분포
        </h5>
        <div className="space-y-1">
          {topNodes.map(([label, count]) => {
            const pct = stats.total_nodes > 0 ? (count / stats.total_nodes) * 100 : 0;
            return (
              <div key={label} className="flex items-center gap-2 text-xs">
                <div
                  className="size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: getNodeColor(label) }}
                />
                <span className="truncate flex-1">{label}</span>
                <Badge variant="secondary" className="text-[9px] px-1 h-4">
                  {count}
                </Badge>
                <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.max(pct, 4)}%`,
                      backgroundColor: getNodeColor(label),
                      opacity: 0.7,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Edge type distribution */}
      {topEdges.length > 0 && (
        <div className="border-t px-3 py-2">
          <h5 className="text-[10px] font-semibold uppercase text-muted-foreground mb-1.5">
            엣지 타입 분포
          </h5>
          <div className="space-y-1">
            {topEdges.map(([relType, count]) => {
              const pct = stats.total_edges > 0 ? (count / stats.total_edges) * 100 : 0;
              return (
                <div key={relType} className="flex items-center gap-2 text-xs">
                  <span className="truncate flex-1 text-muted-foreground">{relType}</span>
                  <Badge variant="outline" className="text-[9px] px-1 h-4">
                    {count}
                  </Badge>
                  <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-slate-400"
                      style={{ width: `${Math.max(pct, 4)}%`, opacity: 0.6 }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
