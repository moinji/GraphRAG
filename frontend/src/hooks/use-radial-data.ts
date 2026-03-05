import { useState, useMemo, useCallback } from 'react';
import type { GraphNode, GraphEdge } from '@/types/graph';

export interface UseRadialDataReturn {
  centerNodeId: string | null;
  visibleNodes: GraphNode[];
  visibleEdges: GraphEdge[];
  navigationHistory: string[];
  hoveredNodeId: string | null;
  setHoveredNodeId: (id: string | null) => void;
  navigateTo: (nodeId: string) => void;
  navigateBack: (index: number) => void;
}

/**
 * Manages radial graph state: center node, 1-hop filtering, navigation history.
 */
export function useRadialData(
  rawNodes: GraphNode[],
  rawEdges: GraphEdge[],
  expandNode: (nodeId: string) => Promise<void>,
): UseRadialDataReturn {
  const [centerNodeId, setCenterNodeId] = useState<string | null>(null);
  const [navigationHistory, setNavigationHistory] = useState<string[]>([]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // Auto-select center: highest degree node
  const effectiveCenterId = useMemo(() => {
    if (centerNodeId && rawNodes.some((n) => n.id === centerNodeId)) {
      return centerNodeId;
    }
    if (rawNodes.length === 0) return null;

    const degree = new Map<string, number>();
    for (const n of rawNodes) degree.set(n.id, 0);
    for (const e of rawEdges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    let maxId = rawNodes[0].id;
    let maxDeg = 0;
    for (const [id, deg] of degree) {
      if (deg > maxDeg) {
        maxDeg = deg;
        maxId = id;
      }
    }
    return maxId;
  }, [centerNodeId, rawNodes, rawEdges]);

  // 1-hop filter: center + all direct neighbors
  const { visibleNodes, visibleEdges } = useMemo(() => {
    if (!effectiveCenterId) return { visibleNodes: [], visibleEdges: [] };

    const neighborIds = new Set<string>([effectiveCenterId]);
    const filteredEdges: GraphEdge[] = [];

    for (const e of rawEdges) {
      if (e.source === effectiveCenterId || e.target === effectiveCenterId) {
        neighborIds.add(e.source);
        neighborIds.add(e.target);
        filteredEdges.push(e);
      }
    }

    const filteredNodes = rawNodes.filter((n) => neighborIds.has(n.id));
    return { visibleNodes: filteredNodes, visibleEdges: filteredEdges };
  }, [effectiveCenterId, rawNodes, rawEdges]);

  const navigateTo = useCallback(
    (nodeId: string) => {
      if (nodeId === effectiveCenterId) return;
      setNavigationHistory((prev) => {
        const newHistory = effectiveCenterId ? [...prev, effectiveCenterId] : prev;
        return newHistory;
      });
      setCenterNodeId(nodeId);
      expandNode(nodeId);
    },
    [effectiveCenterId, expandNode],
  );

  const navigateBack = useCallback(
    (index: number) => {
      setNavigationHistory((prev) => {
        const targetId = prev[index];
        if (!targetId) return prev;
        setCenterNodeId(targetId);
        return prev.slice(0, index);
      });
    },
    [],
  );

  return {
    centerNodeId: effectiveCenterId,
    visibleNodes,
    visibleEdges,
    navigationHistory,
    hoveredNodeId,
    setHoveredNodeId,
    navigateTo,
    navigateBack,
  };
}
