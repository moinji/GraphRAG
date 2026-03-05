import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react';
import * as d3 from 'd3';
import type { GraphNode, GraphEdge } from '@/types/graph';
import { getNodeColor } from '@/components/graph/graph-styles';

/** Exposed zoom control handles */
export interface RadialCanvasHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}

interface RadialCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  centerId: string | null;
  onHover: (id: string | null) => void;
  onNavigate: (nodeId: string) => void;
  onSelect: (node: GraphNode) => void;
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  display_name: string;
  isCenter: boolean;
  properties: Record<string, string | number | boolean | null>;
}

interface SimEdge extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  rel_type: string;
}

const ORBIT_RADIUS = 220;
const CENTER_R = 28;
const OUTER_R = 18;
const TRANSITION_MS = 500;

const RadialCanvas = forwardRef<RadialCanvasHandle, RadialCanvasProps>(
  function RadialCanvas({ nodes, edges, centerId, onHover, onNavigate, onSelect }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const svgRef = useRef<SVGSVGElement | null>(null);
    const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

    // Expose zoom controls
    useImperativeHandle(ref, () => ({
      zoomIn: () => {
        if (!svgRef.current || !zoomRef.current) return;
        const svg = d3.select(svgRef.current);
        svg.transition().duration(300).call(zoomRef.current.scaleBy, 1.3);
      },
      zoomOut: () => {
        if (!svgRef.current || !zoomRef.current) return;
        const svg = d3.select(svgRef.current);
        svg.transition().duration(300).call(zoomRef.current.scaleBy, 1 / 1.3);
      },
      fitView: () => {
        if (!svgRef.current || !zoomRef.current) return;
        const svg = d3.select(svgRef.current);
        svg.transition().duration(400).call(zoomRef.current.transform, d3.zoomIdentity);
      },
    }));

    // Build / rebuild simulation when nodes/edges/centerId change
    useEffect(() => {
      const container = containerRef.current;
      if (!container || !centerId) return;

      const width = container.clientWidth;
      const height = container.clientHeight;
      const cx = width / 2;
      const cy = height / 2;

      // Clear previous
      d3.select(container).selectAll('svg').remove();

      const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .style('background', '#fafafa');

      svgRef.current = svg.node();

      // Zoom behaviour
      const zoom = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.2, 4])
        .on('zoom', (event) => {
          g.attr('transform', event.transform);
        });
      zoomRef.current = zoom;
      svg.call(zoom);

      const g = svg.append('g');

      // --- Guideline circles ---
      const guideRadii = [ORBIT_RADIUS * 0.5, ORBIT_RADIUS, ORBIT_RADIUS * 1.5];
      g.selectAll('.guide-circle')
        .data(guideRadii)
        .enter()
        .append('circle')
        .attr('cx', cx)
        .attr('cy', cy)
        .attr('r', (d) => d)
        .attr('fill', 'none')
        .attr('stroke', '#e5e7eb')
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,4');

      // --- Build sim data ---
      const simNodes: SimNode[] = nodes.map((n) => ({
        id: n.id,
        label: n.label,
        display_name: n.display_name,
        isCenter: n.id === centerId,
        properties: n.properties,
        x: n.id === centerId ? cx : undefined,
        y: n.id === centerId ? cy : undefined,
      }));

      const nodeMap = new Map(simNodes.map((n) => [n.id, n]));
      const simEdges: SimEdge[] = edges
        .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
        .map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          rel_type: e.rel_type,
        }));

      // --- Force simulation (run synchronously — no animated ticking) ---
      const simulation = d3.forceSimulation<SimNode>(simNodes)
        .force(
          'link',
          d3.forceLink<SimNode, SimEdge>(simEdges).id((d) => d.id).strength(0),
        )
        .force(
          'radial',
          d3.forceRadial<SimNode>(
            (d) => (d.isCenter ? 0 : ORBIT_RADIUS),
            cx,
            cy,
          ).strength(0.8),
        )
        .force('collision', d3.forceCollide<SimNode>(30))
        .force('charge', d3.forceManyBody<SimNode>().strength(-50))
        .stop(); // prevent animated ticking

      // Pin center node
      const centerSim = simNodes.find((n) => n.isCenter);
      if (centerSim) {
        centerSim.fx = cx;
        centerSim.fy = cy;
      }

      // Pre-compute all positions synchronously
      for (let i = 0; i < 300; i++) simulation.tick();

      // --- Edge elements (arc paths) ---
      const edgeGroup = g.append('g').attr('class', 'edges');
      const edgePaths = edgeGroup
        .selectAll<SVGPathElement, SimEdge>('path')
        .data(simEdges, (d) => d.id)
        .enter()
        .append('path')
        .attr('fill', 'none')
        .attr('stroke', '#cbd5e1')
        .attr('stroke-width', 1.5)
        .attr('marker-end', 'url(#arrow)');

      // Arrow marker
      svg.append('defs').append('marker')
        .attr('id', 'arrow')
        .attr('viewBox', '0 0 10 10')
        .attr('refX', 10)
        .attr('refY', 5)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,0 L10,5 L0,10 Z')
        .attr('fill', '#cbd5e1');

      // --- Edge label group ---
      const edgeLabelGroup = g.append('g').attr('class', 'edge-labels');
      const edgeLabels = edgeLabelGroup
        .selectAll<SVGTextElement, SimEdge>('text')
        .data(simEdges, (d) => d.id)
        .enter()
        .append('text')
        .text((d) => d.rel_type)
        .attr('font-size', '8px')
        .attr('fill', '#9ca3af')
        .attr('text-anchor', 'middle')
        .attr('dy', -4);

      // --- Node elements ---
      const nodeGroup = g.append('g').attr('class', 'nodes');
      const nodeGs = nodeGroup
        .selectAll<SVGGElement, SimNode>('g')
        .data(simNodes, (d) => d.id)
        .enter()
        .append('g')
        .style('cursor', 'pointer');

      // Drop shadow for center
      const defs = svg.select('defs');
      const filter = defs.append('filter').attr('id', 'drop-shadow');
      filter.append('feDropShadow')
        .attr('dx', 0).attr('dy', 2)
        .attr('stdDeviation', 3)
        .attr('flood-color', '#00000030');

      // Node circles
      nodeGs
        .append('circle')
        .attr('r', (d) => (d.isCenter ? CENTER_R : OUTER_R))
        .attr('fill', (d) => getNodeColor(d.label))
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .attr('filter', (d) => (d.isCenter ? 'url(#drop-shadow)' : null));

      // Node labels
      nodeGs
        .append('text')
        .text((d) => {
          const name = d.display_name;
          return name.length > 12 ? name.slice(0, 11) + '\u2026' : name;
        })
        .attr('text-anchor', 'middle')
        .attr('dy', (d) => (d.isCenter ? CENTER_R + 14 : OUTER_R + 14))
        .attr('font-size', (d) => (d.isCenter ? '12px' : '10px'))
        .attr('font-weight', (d) => (d.isCenter ? '600' : '400'))
        .attr('fill', '#374151');

      // Label type badge (small text above node)
      nodeGs
        .append('text')
        .text((d) => d.label)
        .attr('text-anchor', 'middle')
        .attr('dy', (d) => -(d.isCenter ? CENTER_R + 6 : OUTER_R + 6))
        .attr('font-size', '8px')
        .attr('fill', '#9ca3af');

      // --- Interactions ---
      nodeGs.on('click', (_event, d) => {
        if (d.isCenter) {
          // Select for detail panel
          const original = nodes.find((n) => n.id === d.id);
          if (original) onSelect(original);
        } else {
          onNavigate(d.id);
        }
      });

      // Hover highlight — handled entirely in D3 (no React re-render)
      nodeGs.on('mouseenter', (_event, d) => {
        onHover(d.id);
        const connNodeIds = new Set<string>([d.id]);
        const connEdgeIds = new Set<string>();
        for (const e of simEdges) {
          const sid = typeof e.source === 'object' ? (e.source as SimNode).id : e.source;
          const tid = typeof e.target === 'object' ? (e.target as SimNode).id : e.target;
          if (sid === d.id || tid === d.id) {
            connNodeIds.add(sid);
            connNodeIds.add(tid);
            connEdgeIds.add(e.id);
          }
        }
        nodeGs.attr('opacity', (n) => (connNodeIds.has(n.id) ? 1 : 0.15));
        edgePaths.attr('opacity', (e) => (connEdgeIds.has(e.id) ? 1 : 0.08))
          .attr('stroke', (e) => (connEdgeIds.has(e.id) ? '#6366f1' : '#cbd5e1'));
        edgeLabels.attr('opacity', (e) => (connEdgeIds.has(e.id) ? 1 : 0.08));
      });

      nodeGs.on('mouseleave', () => {
        onHover(null);
        nodeGs.attr('opacity', 1);
        edgePaths.attr('opacity', 1).attr('stroke', '#cbd5e1');
        edgeLabels.attr('opacity', 1);
      });

      // --- Arc path helper ---
      function arcPath(s: SimNode, t: SimNode): string {
        const dx = (t.x ?? 0) - (s.x ?? 0);
        const dy = (t.y ?? 0) - (s.y ?? 0);
        const dr = Math.sqrt(dx * dx + dy * dy) * 1.2;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const targetR = t.isCenter ? CENTER_R : OUTER_R;
        const offsetX = (dx / dist) * targetR;
        const offsetY = (dy / dist) * targetR;
        return `M${s.x},${s.y} A${dr},${dr} 0 0,1 ${(t.x ?? 0) - offsetX},${(t.y ?? 0) - offsetY}`;
      }

      // --- Render static positions (simulation already computed) ---
      edgePaths.attr('d', (d) => {
        const s = d.source as SimNode;
        const t = d.target as SimNode;
        return arcPath(s, t);
      });

      edgeLabels
        .attr('x', (d) => {
          const s = d.source as SimNode;
          const t = d.target as SimNode;
          return ((s.x ?? 0) + (t.x ?? 0)) / 2;
        })
        .attr('y', (d) => {
          const s = d.source as SimNode;
          const t = d.target as SimNode;
          return ((s.y ?? 0) + (t.y ?? 0)) / 2;
        });

      nodeGs.attr('transform', (d) => `translate(${d.x},${d.y})`);

      // Fade-in entrance
      nodeGs.attr('opacity', 0)
        .transition()
        .duration(TRANSITION_MS)
        .attr('opacity', 1);

      edgePaths.attr('opacity', 0)
        .transition()
        .duration(TRANSITION_MS)
        .attr('opacity', 1);
    }, [nodes, edges, centerId, onNavigate, onSelect, onHover]);


    return <div ref={containerRef} className="w-full h-full" />;
  },
);

export default RadialCanvas;
