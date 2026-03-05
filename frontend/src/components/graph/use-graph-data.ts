import { useState, useEffect, useCallback, useMemo } from 'react';
import type { ElementDefinition } from 'cytoscape';
import { fetchGraph, fetchGraphStats, fetchNeighbors } from '@/api/client';
import type { GraphData, GraphNode, GraphEdge, GraphStats } from '@/types/graph';
import { getNodeColor } from './graph-styles';

export interface UseGraphDataReturn {
  elements: ElementDefinition[];
  stats: GraphStats | null;
  loading: boolean;
  error: string | null;
  selectedNode: GraphNode | null;
  setSelectedNode: (node: GraphNode | null) => void;
  visibleLabels: Set<string>;
  toggleLabel: (label: string) => void;
  visibleEdgeTypes: Set<string>;
  toggleEdgeType: (edgeType: string) => void;
  searchTerm: string;
  setSearchTerm: (term: string) => void;
  matchedNodeIds: Set<string>;
  expandNode: (nodeId: string) => Promise<void>;
  reload: () => Promise<void>;
  allLabels: string[];
  allEdgeTypes: string[];
  rawNodes: GraphNode[];
  rawEdges: GraphEdge[];
  totalNodes: number;
  totalEdges: number;
  truncated: boolean;
  highlightNodeIds: Set<string>;
  setHighlightNodeIds: (ids: Set<string>) => void;
}

export function useGraphData(limit: number = 500): UseGraphDataReturn {
  const [rawNodes, setRawNodes] = useState<GraphNode[]>([]);
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([]);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [visibleLabels, setVisibleLabels] = useState<Set<string>>(new Set());
  const [visibleEdgeTypes, setVisibleEdgeTypes] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [totalNodes, setTotalNodes] = useState(0);
  const [totalEdges, setTotalEdges] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [highlightNodeIds, setHighlightNodeIds] = useState<Set<string>>(new Set());

  // Derive all labels and edge types
  const allLabels = useMemo(() => {
    const labels = new Set(rawNodes.map((n) => n.label));
    return Array.from(labels).sort();
  }, [rawNodes]);

  const allEdgeTypes = useMemo(() => {
    const types = new Set(rawEdges.map((e) => e.rel_type));
    return Array.from(types).sort();
  }, [rawEdges]);

  // Search matching
  const matchedNodeIds = useMemo(() => {
    if (!searchTerm.trim()) return new Set<string>();
    const lower = searchTerm.toLowerCase();
    const matched = new Set<string>();
    for (const n of rawNodes) {
      if (
        n.display_name.toLowerCase().includes(lower) ||
        n.id.toLowerCase().includes(lower) ||
        n.label.toLowerCase().includes(lower)
      ) {
        matched.add(n.id);
      }
    }
    return matched;
  }, [rawNodes, searchTerm]);

  // Convert to Cytoscape elements with filtering
  const elements = useMemo(() => {
    const els: ElementDefinition[] = [];

    const visibleNodeIds = new Set<string>();
    for (const n of rawNodes) {
      if (!visibleLabels.has(n.label)) continue;
      visibleNodeIds.add(n.id);
      // Exclude id/label/display_name from properties to avoid overriding Cytoscape keys
      const { id: _id, label: _lbl, display_name: _dn, ...safeProps } = n.properties as Record<string, unknown>;
      els.push({
        data: {
          id: n.id,
          label: n.label,
          display_name: n.display_name,
          ...safeProps,
        },
        style: {
          'background-color': getNodeColor(n.label),
        },
      });
    }

    for (const e of rawEdges) {
      if (!visibleEdgeTypes.has(e.rel_type)) continue;
      if (!visibleNodeIds.has(e.source) || !visibleNodeIds.has(e.target)) continue;
      const { id: _eid, source: _es, target: _et, rel_type: _ert, ...safeEdgeProps } = e.properties as Record<string, unknown>;
      els.push({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          rel_type: e.rel_type,
          ...safeEdgeProps,
        },
      });
    }

    return els;
  }, [rawNodes, rawEdges, visibleLabels, visibleEdgeTypes]);

  // Reload graph data from Neo4j
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [graphData, statsData] = await Promise.all([
        fetchGraph(limit),
        fetchGraphStats(),
      ]);

      setRawNodes(graphData.nodes);
      setRawEdges(graphData.edges);
      setTotalNodes(graphData.total_nodes);
      setTotalEdges(graphData.total_edges);
      setTruncated(graphData.truncated);
      setStats(statsData);
      setSelectedNode(null);

      // Initialize all labels/edge types as visible
      const labels = new Set(graphData.nodes.map((n) => n.label));
      setVisibleLabels(labels);
      const edgeTypes = new Set(graphData.edges.map((e) => e.rel_type));
      setVisibleEdgeTypes(edgeTypes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load graph');
    } finally {
      setLoading(false);
    }
  }, [limit]);

  // Initial load
  useEffect(() => {
    reload();
  }, [reload]);

  const toggleLabel = useCallback((label: string) => {
    setVisibleLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  }, []);

  const toggleEdgeType = useCallback((edgeType: string) => {
    setVisibleEdgeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(edgeType)) {
        next.delete(edgeType);
      } else {
        next.add(edgeType);
      }
      return next;
    });
  }, []);

  const expandNode = useCallback(async (nodeId: string) => {
    try {
      const data: GraphData = await fetchNeighbors(nodeId, 1);
      setRawNodes((prev) => {
        const existingIds = new Set(prev.map((n) => n.id));
        const newNodes = data.nodes.filter((n) => !existingIds.has(n.id));
        if (newNodes.length === 0) return prev;
        // Add new labels to visible set
        for (const n of newNodes) {
          setVisibleLabels((vl) => new Set(vl).add(n.label));
        }
        return [...prev, ...newNodes];
      });
      setRawEdges((prev) => {
        const existingIds = new Set(prev.map((e) => e.id));
        const newEdges = data.edges.filter((e) => !existingIds.has(e.id));
        if (newEdges.length === 0) return prev;
        for (const e of newEdges) {
          setVisibleEdgeTypes((ve) => new Set(ve).add(e.rel_type));
        }
        return [...prev, ...newEdges];
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to expand node');
    }
  }, []);

  return {
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
  };
}
