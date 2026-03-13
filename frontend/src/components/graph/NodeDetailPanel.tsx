import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getNodeColor } from './graph-styles';
import type { GraphNode, GraphEdge } from '@/types/graph';

interface NodeDetailPanelProps {
  node: GraphNode;
  edges: GraphEdge[];
  allNodes: GraphNode[];
  onClose: () => void;
  onExpand: (nodeId: string) => void;
  onNavigate: (nodeId: string) => void;
}

export default function NodeDetailPanel({
  node,
  edges,
  allNodes,
  onClose,
  onExpand,
  onNavigate,
}: NodeDetailPanelProps) {
  const [showAllProps, setShowAllProps] = useState(false);

  // Find connected edges
  const connectedEdges = edges.filter(
    (e) => e.source === node.id || e.target === node.id,
  );

  // Build neighbor list
  const neighbors = connectedEdges.map((e) => {
    const isSource = e.source === node.id;
    const neighborId = isSource ? e.target : e.source;
    const neighborNode = allNodes.find((n) => n.id === neighborId);
    return {
      id: neighborId,
      name: neighborNode?.display_name ?? neighborId,
      label: neighborNode?.label ?? 'Unknown',
      relType: e.rel_type,
      direction: isSource ? 'outgoing' as const : 'incoming' as const,
    };
  });

  // Group neighbors by relationship type
  const grouped = neighbors.reduce<Record<string, typeof neighbors>>((acc, nb) => {
    const key = `${nb.direction === 'outgoing' ? '\u2192' : '\u2190'} ${nb.relType}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(nb);
    return acc;
  }, {});

  // Connection summary
  const outCount = neighbors.filter((n) => n.direction === 'outgoing').length;
  const inCount = neighbors.filter((n) => n.direction === 'incoming').length;

  // Properties
  const displayProps = Object.entries(node.properties).filter(
    ([key]) => !key.startsWith('_') && key !== 'id' && key !== 'label' && key !== 'display_name',
  );
  const visibleProps = showAllProps ? displayProps : displayProps.slice(0, 6);
  const hasMore = displayProps.length > 6;

  function copyProps() {
    const text = displayProps
      .map(([k, v]) => `${k}: ${String(v ?? 'null')}`)
      .join('\n');
    navigator.clipboard.writeText(text);
    toast.success('속성이 복사되었습니다');
  }

  return (
    <div className="flex h-full w-72 flex-col border-l bg-background">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <div
            className="size-3 rounded-full"
            style={{ backgroundColor: getNodeColor(node.label) }}
          />
          <span className="text-sm font-semibold">{node.label}</span>
        </div>
        <button
          onClick={onClose}
          aria-label="닫기"
          className="text-muted-foreground hover:text-foreground text-lg leading-none"
        >
          &times;
        </button>
      </div>

      {/* Node name */}
      <div className="border-b px-4 py-3">
        <p className="text-base font-medium">{node.display_name}</p>
        <p className="text-xs text-muted-foreground mt-1">{node.id}</p>
      </div>

      {/* Properties */}
      <div className="flex-1 overflow-y-auto">
        {displayProps.length > 0 && (
          <div className="border-b px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">
                속성 ({displayProps.length})
              </h4>
              <button
                onClick={copyProps}
                title="속성 복사"
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                복사
              </button>
            </div>
            <dl className="space-y-1.5">
              {visibleProps.map(([key, value]) => (
                <div key={key} className="flex items-start gap-2 text-sm">
                  <dt className="text-muted-foreground min-w-0 shrink-0">{key}:</dt>
                  <dd className="break-all">{String(value ?? 'null')}</dd>
                </div>
              ))}
            </dl>
            {hasMore && (
              <button
                onClick={() => setShowAllProps(!showAllProps)}
                className="text-xs text-primary mt-2 hover:underline"
              >
                {showAllProps ? '접기' : `+${displayProps.length - 6}개 더보기`}
              </button>
            )}
          </div>
        )}

        {/* Connection summary */}
        <div className="border-b px-4 py-2 flex gap-3 text-xs text-muted-foreground">
          <span>연결 {neighbors.length}</span>
          <span>나가는 {outCount}</span>
          <span>들어오는 {inCount}</span>
        </div>

        {/* Connected nodes (grouped) */}
        <div className="px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase">
              연결 노드
            </h4>
            <Button variant="outline" size="xs" onClick={() => onExpand(node.id)}>
              확장
            </Button>
          </div>
          {neighbors.length === 0 ? (
            <p className="text-sm text-muted-foreground">연결 없음</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(grouped).map(([groupKey, nbs]) => (
                <div key={groupKey}>
                  <div className="flex items-center gap-1 mb-1">
                    <span className="text-xs font-medium text-muted-foreground">{groupKey}</span>
                    <Badge variant="outline" className="text-[9px] px-1">{nbs.length}</Badge>
                  </div>
                  <ul className="space-y-0.5">
                    {nbs.map((nb, i) => (
                      <li key={`${nb.id}-${i}`}>
                        <button
                          onClick={() => onNavigate(nb.id)}
                          className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-accent"
                        >
                          <div
                            className="size-2 shrink-0 rounded-full"
                            style={{ backgroundColor: getNodeColor(nb.label) }}
                          />
                          <span className="truncate flex-1">{nb.name}</span>
                          <span className="text-[10px] text-muted-foreground shrink-0">{nb.label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
