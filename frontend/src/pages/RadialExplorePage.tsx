import { useRef, useCallback, useState } from 'react';
import GraphFilterSidebar from '@/components/graph/GraphFilterSidebar';
import NodeDetailPanel from '@/components/graph/NodeDetailPanel';
import RadialCanvas from '@/components/radial/RadialCanvas';
import type { RadialCanvasHandle } from '@/components/radial/RadialCanvas';
import RadialToolbar from '@/components/radial/RadialToolbar';
import { useRadialData } from '@/hooks/use-radial-data';
import { DEMO_QUESTIONS } from '@/constants';
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
  highlightNodeIds?: Set<string>;
  demoAnswer?: string | null;
  onDemoQuestion?: (question: string) => void;
  demoQueryLoading?: boolean;
  onClearDemo?: () => void;
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
  highlightNodeIds,
  demoAnswer,
  onDemoQuestion,
  demoQueryLoading,
  onClearDemo,
}: RadialExplorePageProps) {
  const canvasRef = useRef<RadialCanvasHandle>(null);

  const {
    centerNodeId,
    visibleNodes,
    visibleEdges,
    navigationHistory,
    hoveredNodeId: _hoveredNodeId,
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

  const [demoOpen, setDemoOpen] = useState(false);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center gap-2">
        <div className="flex-1">
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
        </div>
        {/* Demo Q&A dropdown */}
        {onDemoQuestion && (
          <div className="relative mr-2">
            <button
              onClick={() => setDemoOpen((v) => !v)}
              disabled={demoQueryLoading}
              className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-accent disabled:opacity-50"
            >
              {demoQueryLoading ? '분석 중...' : 'Demo Q&A ▾'}
            </button>
            {demoOpen && (
              <div className="absolute right-0 top-full z-30 mt-1 w-72 rounded-md border bg-background shadow-lg">
                {DEMO_QUESTIONS.map((q) => (
                  <button
                    key={q.label}
                    onClick={() => { onDemoQuestion(q.text); setDemoOpen(false); }}
                    className="block w-full text-left px-3 py-2 text-xs hover:bg-accent border-b last:border-b-0"
                  >
                    <span className="inline-block mr-1 px-1 rounded text-[10px] font-semibold bg-violet-600 text-white">
                      {q.label}
                    </span>
                    {q.text}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Demo answer banner */}
      {demoAnswer && (
        <div className="flex items-center gap-3 border-b bg-violet-50 px-4 py-2 text-sm">
          <span className="flex-1 text-violet-900">{demoAnswer}</span>
          {onClearDemo && (
            <button
              onClick={onClearDemo}
              className="text-violet-600 hover:text-violet-800 font-medium whitespace-nowrap text-xs"
            >
              지우기
            </button>
          )}
        </div>
      )}

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
              highlightNodeIds={highlightNodeIds}
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
