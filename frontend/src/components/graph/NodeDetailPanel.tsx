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
      direction: isSource ? 'outgoing' : 'incoming',
    };
  });

  // Filter out non-cytoscape internal properties for display
  const displayProps = Object.entries(node.properties).filter(
    ([key]) => !key.startsWith('_') && key !== 'id' && key !== 'label' && key !== 'display_name',
  );

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
            <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
              속성 (Properties)
            </h4>
            <dl className="space-y-1.5">
              {displayProps.map(([key, value]) => (
                <div key={key} className="flex items-start gap-2 text-sm">
                  <dt className="text-muted-foreground min-w-0 shrink-0">{key}:</dt>
                  <dd className="break-all">{String(value ?? 'null')}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {/* Connected nodes */}
        <div className="px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase">
              연결 ({neighbors.length})
            </h4>
            <Button variant="outline" size="xs" onClick={() => onExpand(node.id)}>
              확장
            </Button>
          </div>
          {neighbors.length === 0 ? (
            <p className="text-sm text-muted-foreground">연결 없음</p>
          ) : (
            <ul className="space-y-1.5">
              {neighbors.map((nb, i) => (
                <li key={`${nb.id}-${i}`}>
                  <button
                    onClick={() => onNavigate(nb.id)}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
                  >
                    <div
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: getNodeColor(nb.label) }}
                    />
                    <span className="truncate">{nb.name}</span>
                    <Badge variant="outline" className="ml-auto text-[10px] shrink-0">
                      {nb.direction === 'outgoing' ? '\u2192' : '\u2190'} {nb.relType}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
