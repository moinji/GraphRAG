import { useState, useEffect, useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { computeOntologyDiff } from '@/api/client';
import type { OntologyDiff } from '@/types/ontology';
import type { GraphNode, GraphEdge } from '@/types/graph';

interface GraphDiffOverlayProps {
  rawNodes: GraphNode[];
  rawEdges: GraphEdge[];
  onHighlight: (nodeIds: Set<string>) => void;
}

type DiffColor = 'added' | 'removed' | 'modified' | null;

interface DiffSummaryEntry {
  name: string;
  type: 'node' | 'edge';
  change: 'added' | 'removed' | 'modified';
  count: number;
}

const CHANGE_COLORS = {
  added: { bg: '#dcfce7', border: '#16a34a', text: '#15803d', label: '추가' },
  removed: { bg: '#fecaca', border: '#dc2626', text: '#b91c1c', label: '삭제' },
  modified: { bg: '#fef9c3', border: '#ca8a04', text: '#a16207', label: '변경' },
} as const;

export default function GraphDiffOverlay({ rawNodes, rawEdges, onHighlight }: GraphDiffOverlayProps) {
  const [visible, setVisible] = useState(false);
  const [baseVersion, setBaseVersion] = useState('');
  const [targetVersion, setTargetVersion] = useState('');
  const [diff, setDiff] = useState<OntologyDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<DiffColor>(null);

  // Compute which graph nodes are affected by the diff
  const affectedNodes = useMemo(() => {
    if (!diff) return new Map<string, DiffColor>();
    const map = new Map<string, DiffColor>();

    for (const nd of diff.node_diffs) {
      // Find matching graph nodes by label
      const matching = rawNodes.filter(
        (n) => n.label.toLowerCase() === nd.name.toLowerCase(),
      );
      for (const n of matching) {
        map.set(n.id, nd.change_type as DiffColor);
      }
    }
    return map;
  }, [diff, rawNodes]);

  // Build summary entries
  const summaryEntries = useMemo((): DiffSummaryEntry[] => {
    if (!diff) return [];
    const entries: DiffSummaryEntry[] = [];

    for (const nd of diff.node_diffs) {
      const count = rawNodes.filter(
        (n) => n.label.toLowerCase() === nd.name.toLowerCase(),
      ).length;
      entries.push({
        name: nd.name,
        type: 'node',
        change: nd.change_type,
        count,
      });
    }

    for (const rd of diff.relationship_diffs) {
      const count = rawEdges.filter(
        (e) => e.rel_type.toLowerCase() === rd.name.toLowerCase(),
      ).length;
      entries.push({
        name: rd.name,
        type: 'edge',
        change: rd.change_type,
        count,
      });
    }

    return entries;
  }, [diff, rawNodes, rawEdges]);

  // Update highlight when filter changes
  useEffect(() => {
    if (!diff || !activeFilter) {
      onHighlight(new Set());
      return;
    }

    const ids = new Set<string>();
    for (const [nodeId, color] of affectedNodes) {
      if (color === activeFilter) ids.add(nodeId);
    }
    onHighlight(ids);
  }, [activeFilter, affectedNodes, diff, onHighlight]);

  async function handleLoadDiff() {
    const base = parseInt(baseVersion, 10);
    const target = parseInt(targetVersion, 10);
    if (isNaN(base) || isNaN(target)) {
      setError('유효한 버전 ID를 입력하세요');
      return;
    }
    setLoading(true);
    setError(null);
    setActiveFilter(null);
    try {
      const result = await computeOntologyDiff(base, target);
      setDiff(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Diff 계산 실패');
      setDiff(null);
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setDiff(null);
    setActiveFilter(null);
    onHighlight(new Set());
  }

  if (!visible) {
    return (
      <button
        onClick={() => setVisible(true)}
        className="absolute top-3 right-3 z-10 rounded-lg border bg-background/90 px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur hover:bg-accent"
      >
        Diff 오버레이
      </button>
    );
  }

  const totalChanges = diff
    ? diff.node_diffs.length + diff.relationship_diffs.length
    : 0;

  return (
    <div className="absolute top-3 right-3 z-10 w-72 rounded-lg border bg-background/95 shadow-lg backdrop-blur">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">
          스키마 Diff 오버레이
        </h4>
        <button
          onClick={() => { setVisible(false); handleClear(); }}
          className="text-muted-foreground hover:text-foreground text-lg leading-none"
        >
          &times;
        </button>
      </div>

      {/* Version inputs */}
      <div className="flex gap-2 p-3">
        <input
          type="number"
          placeholder="Base ver."
          value={baseVersion}
          onChange={(e) => setBaseVersion(e.target.value)}
          className="w-0 flex-1 rounded border px-2 py-1 text-xs"
          min={1}
        />
        <span className="self-center text-xs text-muted-foreground">&rarr;</span>
        <input
          type="number"
          placeholder="Target ver."
          value={targetVersion}
          onChange={(e) => setTargetVersion(e.target.value)}
          className="w-0 flex-1 rounded border px-2 py-1 text-xs"
          min={1}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handleLoadDiff}
          disabled={loading || !baseVersion || !targetVersion}
          className="text-xs px-2"
        >
          {loading ? '...' : '비교'}
        </Button>
      </div>

      {error && (
        <p className="px-3 pb-2 text-xs text-destructive">{error}</p>
      )}

      {/* Diff results */}
      {diff && (
        <>
          {/* Summary bar */}
          <div className="flex items-center gap-2 border-t px-3 py-2">
            <span className="text-xs text-muted-foreground">
              v{diff.base_version_id} &rarr; v{diff.target_version_id}
            </span>
            <Badge variant={diff.is_breaking ? 'destructive' : 'secondary'} className="text-[9px]">
              {diff.is_breaking ? 'BREAKING' : 'SAFE'}
            </Badge>
            <span className="ml-auto text-xs text-muted-foreground">
              {totalChanges}건
            </span>
          </div>

          {/* Filter buttons */}
          <div className="flex gap-1.5 px-3 py-1.5">
            {(['added', 'removed', 'modified'] as const).map((type) => {
              const count = summaryEntries.filter((e) => e.change === type).length;
              if (count === 0) return null;
              const colors = CHANGE_COLORS[type];
              const isActive = activeFilter === type;
              return (
                <button
                  key={type}
                  onClick={() => setActiveFilter(isActive ? null : type)}
                  className="rounded-md px-2 py-0.5 text-[10px] font-medium border transition-colors"
                  style={{
                    backgroundColor: isActive ? colors.bg : 'transparent',
                    borderColor: isActive ? colors.border : '#e5e7eb',
                    color: isActive ? colors.text : '#6b7280',
                  }}
                >
                  {colors.label} {count}
                </button>
              );
            })}
            {activeFilter && (
              <button
                onClick={() => setActiveFilter(null)}
                className="text-[10px] text-muted-foreground hover:text-foreground ml-auto"
              >
                초기화
              </button>
            )}
          </div>

          {/* Change list */}
          <div className="max-h-48 overflow-y-auto border-t px-3 py-2">
            {summaryEntries.length === 0 ? (
              <p className="text-xs text-muted-foreground">변경 사항 없음</p>
            ) : (
              <ul className="space-y-1">
                {summaryEntries.map((entry) => {
                  const colors = CHANGE_COLORS[entry.change];
                  return (
                    <li
                      key={`${entry.type}-${entry.name}`}
                      className="flex items-center gap-2 text-xs rounded px-1.5 py-0.5"
                      style={{ backgroundColor: colors.bg + '40' }}
                    >
                      <span
                        className="size-1.5 shrink-0 rounded-full"
                        style={{ backgroundColor: colors.border }}
                      />
                      <Badge
                        variant="outline"
                        className="text-[8px] px-1 h-3.5"
                        style={{ borderColor: colors.border, color: colors.text }}
                      >
                        {entry.type === 'node' ? 'N' : 'E'}
                      </Badge>
                      <span className="truncate flex-1" style={{ color: colors.text }}>
                        {entry.name}
                      </span>
                      {entry.count > 0 && (
                        <span className="text-[10px] text-muted-foreground">
                          ({entry.count}개)
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Legend + Clear */}
          <div className="flex items-center justify-between border-t px-3 py-2">
            <div className="flex gap-2 text-[10px]">
              {(['added', 'removed', 'modified'] as const).map((type) => (
                <span key={type} className="flex items-center gap-1">
                  <span
                    className="inline-block size-2 rounded-full"
                    style={{ backgroundColor: CHANGE_COLORS[type].border }}
                  />
                  {CHANGE_COLORS[type].label}
                </span>
              ))}
            </div>
            <button
              onClick={handleClear}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              닫기
            </button>
          </div>
        </>
      )}
    </div>
  );
}
