import { useState, useRef, useCallback, useEffect } from 'react';
import type cytoscape from 'cytoscape';
import GraphCanvas from '@/components/graph/GraphCanvas';
import GraphToolbar from '@/components/graph/GraphToolbar';
import GraphFilterSidebar from '@/components/graph/GraphFilterSidebar';
import NodeDetailPanel from '@/components/graph/NodeDetailPanel';
import RadialExplorePage from '@/pages/RadialExplorePage';
import { useGraphData } from '@/components/graph/use-graph-data';
import type { LayoutName } from '@/components/graph/graph-layouts';
import { sendQuery, resetGraph } from '@/api/client';
import { GRAPH_DEFAULT_LIMIT } from '@/constants';

type ViewMode = 'classic' | 'radial';

function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false,
  );
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < breakpoint);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [breakpoint]);
  return isMobile;
}

interface ExplorePageProps {
  onBack: () => void;
}

export default function ExplorePage({ onBack }: ExplorePageProps) {
  const {
    elements,
    stats,
    loading,
    error,
    selectedNode,
    setSelectedNode,
    visibleLabels,
    toggleLabel,
    visibleEdgeTypes,
    toggleEdgeType,
    searchTerm,
    setSearchTerm,
    matchedNodeIds,
    expandNode,
    reload,
    allLabels,
    allEdgeTypes,
    rawNodes,
    rawEdges,
    totalNodes,
    totalEdges,
    truncated,
    highlightNodeIds,
    setHighlightNodeIds,
  } = useGraphData(GRAPH_DEFAULT_LIMIT);

  const isMobile = useIsMobile();
  const [viewMode, setViewMode] = useState<ViewMode>('classic');
  const [layout, setLayout] = useState<LayoutName>('cose');
  const [demoQueryLoading, setDemoQueryLoading] = useState(false);
  const [demoAnswer, setDemoAnswer] = useState<string | null>(null);
  const [resetLoading, setResetLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const cyRef = useRef<cytoscape.Core | null>(null);

  const handleZoomIn = useCallback(() => {
    const cy = cyRef.current;
    if (cy) {
      cy.zoom({
        level: cy.zoom() * 1.3,
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
      });
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    const cy = cyRef.current;
    if (cy) {
      cy.zoom({
        level: cy.zoom() / 1.3,
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
      });
    }
  }, []);

  const handleFitView = useCallback(() => {
    cyRef.current?.fit(undefined, 40);
  }, []);

  const handleNavigate = useCallback(
    (nodeId: string) => {
      const node = rawNodes.find((n) => n.id === nodeId);
      if (node) {
        setSelectedNode(node);
        const cy = cyRef.current;
        if (cy) {
          const ele = cy.getElementById(nodeId);
          if (ele.length > 0) {
            cy.animate({ center: { eles: ele }, zoom: 1.5 }, { duration: 400 });
          }
        }
      }
    },
    [rawNodes, setSelectedNode],
  );

  const handleDemoQuestion = useCallback(
    async (question: string) => {
      setDemoQueryLoading(true);
      setHighlightNodeIds(new Set());
      setDemoAnswer(null);
      try {
        const res = await sendQuery(question, 'a');
        setDemoAnswer(res.answer);
        if (res.related_node_ids && res.related_node_ids.length > 0) {
          setHighlightNodeIds(new Set(res.related_node_ids));
        }
      } catch {
        setDemoAnswer('Query failed. Please try again.');
      } finally {
        setDemoQueryLoading(false);
      }
    },
    [setHighlightNodeIds],
  );

  const handleClearDemo = useCallback(() => {
    setHighlightNodeIds(new Set());
    setDemoAnswer(null);
  }, [setHighlightNodeIds]);

  const handleReset = useCallback(async () => {
    if (!window.confirm(`그래프를 초기화하시겠습니까? ${totalNodes}개 노드와 ${totalEdges}개 엣지가 삭제됩니다.`)) return;
    setResetLoading(true);
    try {
      await resetGraph();
      await reload();
    } catch {
      // reload will show error state if Neo4j is down
    } finally {
      setResetLoading(false);
    }
  }, [totalNodes, totalEdges, reload]);

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-57px)] items-center justify-center">
        <div className="text-center">
          <div className="animate-spin inline-block size-8 border-2 border-current border-t-transparent rounded-full text-muted-foreground" />
          <p className="mt-3 text-sm text-muted-foreground">그래프 로딩 중...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[calc(100vh-57px)] items-center justify-center">
        <div className="text-center max-w-md">
          <p className="text-sm text-destructive font-medium">그래프 로드 실패</p>
          <p className="text-sm text-muted-foreground mt-1">{error}</p>
          <p className="text-xs text-muted-foreground mt-3">
            먼저 Knowledge Graph를 빌드하세요 (DDL 업로드 &rarr; KG 빌드).
          </p>
        </div>
      </div>
    );
  }

  if (rawNodes.length === 0) {
    return (
      <div className="flex h-[calc(100vh-57px)] items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-muted-foreground">그래프 데이터 없음</p>
          <p className="text-xs text-muted-foreground mt-1">
            먼저 DDL을 업로드하고 Knowledge Graph를 빌드하세요.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-57px)] flex-col">
      {/* Top bar: Back + View toggle */}
      <div className="flex items-center gap-2 px-3 pt-2">
        <button
          onClick={onBack}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; 뒤로
        </button>
        <div className="ml-auto flex rounded-md border text-sm overflow-hidden">
          <button
            onClick={() => setViewMode('classic')}
            className={`px-3 py-1 ${viewMode === 'classic' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
          >
            Classic
          </button>
          <button
            onClick={() => setViewMode('radial')}
            className={`px-3 py-1 border-l ${viewMode === 'radial' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
          >
            Radial Map
          </button>
        </div>
      </div>

      {viewMode === 'classic' && (
        <>
          <div className="flex items-center gap-1 flex-wrap">
            {/* Mobile sidebar toggle */}
            {isMobile && (
              <button
                onClick={() => setSidebarOpen((v) => !v)}
                className="ml-2 rounded-md border px-2 py-1 text-xs hover:bg-accent"
              >
                {sidebarOpen ? '필터 닫기' : '필터'}
              </button>
            )}
            <div className="flex-1 min-w-0">
              <GraphToolbar
                searchTerm={searchTerm}
                onSearchChange={setSearchTerm}
                layout={layout}
                onLayoutChange={setLayout}
                onZoomIn={handleZoomIn}
                onZoomOut={handleZoomOut}
                onFitView={handleFitView}
                totalNodes={totalNodes}
                totalEdges={totalEdges}
                truncated={truncated}
                onDemoQuestion={handleDemoQuestion}
                demoQueryLoading={demoQueryLoading}
                onReset={handleReset}
                resetLoading={resetLoading}
              />
            </div>
          </div>

          {/* Demo answer banner */}
          {demoAnswer && (
            <div className="flex items-center gap-3 border-b bg-violet-50 px-4 py-2 text-sm">
              <span className="flex-1 text-violet-900">{demoAnswer}</span>
              <button
                onClick={handleClearDemo}
                className="text-violet-600 hover:text-violet-800 font-medium whitespace-nowrap"
              >
                지우기
              </button>
            </div>
          )}

          {/* Main content area */}
          <div className="flex flex-1 overflow-hidden relative">
            {/* Left: Filter sidebar — hidden on mobile, toggleable */}
            {(!isMobile || sidebarOpen) && (
              <div className={isMobile
                ? 'absolute inset-y-0 left-0 z-20 shadow-lg'
                : ''
              }>
                <GraphFilterSidebar
                  allLabels={allLabels}
                  visibleLabels={visibleLabels}
                  onToggleLabel={toggleLabel}
                  allEdgeTypes={allEdgeTypes}
                  visibleEdgeTypes={visibleEdgeTypes}
                  onToggleEdgeType={toggleEdgeType}
                  stats={stats}
                />
              </div>
            )}
            {/* Mobile sidebar backdrop */}
            {isMobile && sidebarOpen && (
              <div
                className="absolute inset-0 z-10 bg-black/20"
                onClick={() => setSidebarOpen(false)}
              />
            )}

            {/* Center: Graph canvas */}
            <div className="flex-1 relative">
              <div className="absolute inset-0">
                <GraphCanvas
                  elements={elements}
                  layout={layout}
                  onNodeSelect={setSelectedNode}
                  matchedNodeIds={matchedNodeIds}
                  highlightNodeIds={highlightNodeIds}
                  visibleLabels={visibleLabels}
                  cyRef={cyRef}
                />
              </div>
            </div>

            {/* Right: Detail panel — overlay on mobile */}
            {selectedNode && (
              <div className={isMobile
                ? 'absolute inset-y-0 right-0 z-20 shadow-lg'
                : ''
              }>
                <NodeDetailPanel
                  node={selectedNode}
                  edges={rawEdges}
                  allNodes={rawNodes}
                  onClose={() => setSelectedNode(null)}
                  onExpand={expandNode}
                  onNavigate={handleNavigate}
                />
              </div>
            )}
          </div>
        </>
      )}

      {viewMode === 'radial' && (
        <RadialExplorePage
          rawNodes={rawNodes}
          rawEdges={rawEdges}
          stats={stats}
          allLabels={allLabels}
          allEdgeTypes={allEdgeTypes}
          visibleLabels={visibleLabels}
          toggleLabel={toggleLabel}
          visibleEdgeTypes={visibleEdgeTypes}
          toggleEdgeType={toggleEdgeType}
          expandNode={expandNode}
          selectedNode={selectedNode}
          setSelectedNode={setSelectedNode}
        />
      )}
    </div>
  );
}
