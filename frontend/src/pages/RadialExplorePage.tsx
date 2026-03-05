import { useRef, useCallback } from 'react';
import GraphFilterSidebar from '@/components/graph/GraphFilterSidebar';
import NodeDetailPanel from '@/components/graph/NodeDetailPanel';
import RadialCanvas from '@/components/radial/RadialCanvas';
import type { RadialCanvasHandle } from '@/components/radial/RadialCanvas';
import RadialToolbar from '@/components/radial/RadialToolbar';
import { useRadialData } from '@/hooks/use-radial-data';
import type { GraphNode, GraphEdge, GraphStats } from '@/types/graph';

interface RadialExplorePageProps {
  rawNodes: GraphNode[];
  rawEdges: GraphEdge[];
  stats: GraphStats | null;
  allLabels: string[];
  allEdgeTypes: string[];
  visibleLabels: Set<string>;
  toggleLabel: (label: string) => void;
  visibleEdgeTypes: Set<string>;
  toggleEdgeType: (edgeType: string) => void;
  expandNode: (nodeId: string) => Promise<void>;
  selectedNode: GraphNode | null;
  setSelectedNode: (node: GraphNode | null) => void;
}

export default function RadialExplorePage({
  rawNodes,
  rawEdges,
  stats,
  allLabels,
  allEdgeTypes,
  visibleLabels,
  toggleLabel,
  visibleEdgeTypes,
  toggleEdgeType,
  expandNode,
  selectedNode,
  setSelectedNode,
}: RadialExplorePageProps) {
  const canvasRef = useRef<RadialCanvasHandle>(null);

  const {
    centerNodeId,
    visibleNodes,
    visibleEdges,
    navigationHistory,
    hoveredNodeId,
    setHoveredNodeId,
    navigateTo,
    navigateBack,
  } = useRadialData(rawNodes, rawEdges, expandNode);

  // Filter visible nodes/edges by sidebar filters
  const filteredNodes = visibleNodes.filter((n) => visibleLabels.has(n.label));
  const filteredEdgeNodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = visibleEdges.filter(
    (e) =>
      visibleEdgeTypes.has(e.rel_type) &&
      filteredEdgeNodeIds.has(e.source) &&
      filteredEdgeNodeIds.has(e.target),
  );

  const centerNode = rawNodes.find((n) => n.id === centerNodeId) ?? null;

  const handleNavigate = useCallback(
    (nodeId: string) => {
      const node = rawNodes.find((n) => n.id === nodeId);
      if (node) setSelectedNode(node);
      navigateTo(nodeId);
    },
    [rawNodes, setSelectedNode, navigateTo],
  );

  const handleSelect = useCallback(
    (node: GraphNode) => {
      setSelectedNode(node);
    },
    [setSelectedNode],
  );

  const handleDetailNavigate = useCallback(
    (nodeId: string) => {
      navigateTo(nodeId);
    },
    [navigateTo],
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <RadialToolbar
        centerNode={centerNode}
        navigationHistory={navigationHistory}
        allNodes={rawNodes}
        edges={rawEdges}
        onNavigateBack={navigateBack}
        onZoomIn={() => canvasRef.current?.zoomIn()}
        onZoomOut={() => canvasRef.current?.zoomOut()}
        onFitView={() => canvasRef.current?.fitView()}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Filter sidebar */}
        <GraphFilterSidebar
          allLabels={allLabels}
          visibleLabels={visibleLabels}
          onToggleLabel={toggleLabel}
          allEdgeTypes={allEdgeTypes}
          visibleEdgeTypes={visibleEdgeTypes}
          onToggleEdgeType={toggleEdgeType}
          stats={stats}
        />

        {/* Center: Radial canvas */}
        <div className="flex-1 relative">
          <div className="absolute inset-0">
            <RadialCanvas
              ref={canvasRef}
              nodes={filteredNodes}
              edges={filteredEdges}
              centerId={centerNodeId}
              onHover={setHoveredNodeId}
              onNavigate={handleNavigate}
              onSelect={handleSelect}
            />
          </div>
        </div>

        {/* Right: Detail panel */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            edges={rawEdges}
            allNodes={rawNodes}
            onClose={() => setSelectedNode(null)}
            onExpand={expandNode}
            onNavigate={handleDetailNavigate}
          />
        )}
      </div>
    </div>
  );
}
