import { useState, useRef, useCallback } from 'react';
import type cytoscape from 'cytoscape';
import GraphCanvas from '@/components/graph/GraphCanvas';
import GraphToolbar from '@/components/graph/GraphToolbar';
import GraphFilterSidebar from '@/components/graph/GraphFilterSidebar';
import NodeDetailPanel from '@/components/graph/NodeDetailPanel';
import { useGraphData } from '@/components/graph/use-graph-data';
import type { LayoutName } from '@/components/graph/graph-layouts';

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
    allLabels,
    allEdgeTypes,
    rawNodes,
    rawEdges,
    totalNodes,
    totalEdges,
    truncated,
  } = useGraphData(500);

  const [layout, setLayout] = useState<LayoutName>('cose');
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

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-57px)] items-center justify-center">
        <div className="text-center">
          <div className="animate-spin inline-block size-8 border-2 border-current border-t-transparent rounded-full text-muted-foreground" />
          <p className="mt-3 text-sm text-muted-foreground">Loading graph...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[calc(100vh-57px)] items-center justify-center">
        <div className="text-center max-w-md">
          <p className="text-sm text-destructive font-medium">Failed to load graph</p>
          <p className="text-sm text-muted-foreground mt-1">{error}</p>
          <p className="text-xs text-muted-foreground mt-3">
            Make sure a Knowledge Graph has been built first (Upload DDL &rarr; Build KG).
          </p>
        </div>
      </div>
    );
  }

  if (rawNodes.length === 0) {
    return (
      <div className="flex h-[calc(100vh-57px)] items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-muted-foreground">No graph data found.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Upload a DDL and build a Knowledge Graph first.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-57px)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 pt-2">
        <button
          onClick={onBack}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back
        </button>
      </div>
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
      />

      {/* Main content area */}
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

        {/* Center: Graph canvas */}
        <div className="flex-1 relative">
          <div className="absolute inset-0">
            <GraphCanvas
              elements={elements}
              layout={layout}
              onNodeSelect={setSelectedNode}
              matchedNodeIds={matchedNodeIds}
              visibleLabels={visibleLabels}
              cyRef={cyRef}
            />
          </div>
        </div>

        {/* Right: Detail panel (conditional) */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            edges={rawEdges}
            allNodes={rawNodes}
            onClose={() => setSelectedNode(null)}
            onExpand={expandNode}
            onNavigate={handleNavigate}
          />
        )}
      </div>
    </div>
  );
}
