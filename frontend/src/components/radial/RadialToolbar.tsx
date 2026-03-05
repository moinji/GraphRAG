import { getNodeColor } from '@/components/graph/graph-styles';
import type { GraphNode, GraphEdge } from '@/types/graph';

interface RadialToolbarProps {
  centerNode: GraphNode | null;
  navigationHistory: string[];
  allNodes: GraphNode[];
  edges: GraphEdge[];
  onNavigateBack: (index: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
}

export default function RadialToolbar({
  centerNode,
  navigationHistory,
  allNodes,
  edges,
  onNavigateBack,
  onZoomIn,
  onZoomOut,
  onFitView,
}: RadialToolbarProps) {
  const getNodeName = (id: string) => {
    const node = allNodes.find((n) => n.id === id);
    return node?.display_name ?? id;
  };

  // Count connections for center node
  const connectionCount = centerNode
    ? edges.filter((e) => e.source === centerNode.id || e.target === centerNode.id).length
    : 0;

  return (
    <div className="flex items-center gap-3 border-b bg-background px-4 py-2">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 flex-1 min-w-0 text-sm overflow-x-auto">
        {navigationHistory.map((nodeId, index) => (
          <span key={`${nodeId}-${index}`} className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => onNavigateBack(index)}
              className="text-muted-foreground hover:text-foreground hover:underline truncate max-w-[120px]"
            >
              {getNodeName(nodeId)}
            </button>
            <span className="text-muted-foreground">&rsaquo;</span>
          </span>
        ))}
        {centerNode && (
          <span className="flex items-center gap-1.5 shrink-0 font-medium">
            <div
              className="size-2.5 rounded-full"
              style={{ backgroundColor: getNodeColor(centerNode.label) }}
            />
            <span>{centerNode.display_name}</span>
            <span className="text-xs text-muted-foreground">
              ({centerNode.label} · {connectionCount} connections)
            </span>
          </span>
        )}
      </div>

      {/* Zoom controls */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={onZoomIn}
          className="rounded px-2 py-1 text-sm border hover:bg-accent"
          title="Zoom In"
        >
          +
        </button>
        <button
          onClick={onZoomOut}
          className="rounded px-2 py-1 text-sm border hover:bg-accent"
          title="Zoom Out"
        >
          &minus;
        </button>
        <button
          onClick={onFitView}
          className="rounded px-2 py-1 text-xs border hover:bg-accent"
          title="Fit View"
        >
          Fit
        </button>
      </div>
    </div>
  );
}
