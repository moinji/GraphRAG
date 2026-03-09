import { useRef, useCallback, useEffect } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import type cytoscape from 'cytoscape';
import type { ElementDefinition } from 'cytoscape';
import type { GraphNode } from '@/types/graph';
import { buildStylesheet } from './graph-styles';
import { LAYOUT_OPTIONS, type LayoutName } from './graph-layouts';

interface GraphCanvasProps {
  elements: ElementDefinition[];
  layout: LayoutName;
  onNodeSelect: (node: GraphNode | null) => void;
  matchedNodeIds: Set<string>;
  highlightNodeIds: Set<string>;
  visibleLabels: Set<string>;
  cyRef?: React.MutableRefObject<cytoscape.Core | null>;
}

export default function GraphCanvas({
  elements,
  layout,
  onNodeSelect,
  matchedNodeIds,
  highlightNodeIds,
  visibleLabels,
  cyRef: externalCyRef,
}: GraphCanvasProps) {
  const internalCyRef = useRef<cytoscape.Core | null>(null);
  const cyRef = externalCyRef ?? internalCyRef;
  const prevLayoutRef = useRef<LayoutName>(layout);

  const handleCy = useCallback(
    (cy: cytoscape.Core) => {
      cyRef.current = cy;

      cy.removeAllListeners();

      cy.on('tap', 'node', (evt) => {
        const nodeData = evt.target.data();
        const props = { ...nodeData };
        delete props.id;
        delete props.label;
        delete props.display_name;
        onNodeSelect({
          id: nodeData.id,
          label: nodeData.label,
          display_name: nodeData.display_name,
          properties: props,
        });
      });

      cy.on('tap', (evt) => {
        if (evt.target === cy) {
          onNodeSelect(null);
        }
      });
    },
    [onNodeSelect, cyRef],
  );

  // Re-run layout when layout name changes
  useEffect(() => {
    if (cyRef.current && prevLayoutRef.current !== layout) {
      prevLayoutRef.current = layout;
      cyRef.current.layout(LAYOUT_OPTIONS[layout]).run();
    }
  }, [layout, cyRef]);

  // Highlight matched search nodes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.nodes().removeClass('search-match');
    if (matchedNodeIds.size > 0) {
      for (const id of matchedNodeIds) {
        const node = cy.getElementById(id);
        if (node.length > 0) {
          node.addClass('search-match');
        }
      }
      // Zoom to first match
      const firstId = matchedNodeIds.values().next().value;
      if (firstId) {
        const firstNode = cy.getElementById(firstId);
        if (firstNode.length > 0) {
          cy.animate(
            { center: { eles: firstNode }, zoom: 1.5 },
            { duration: 400 },
          );
        }
      }
    }
  }, [matchedNodeIds, cyRef]);

  // Highlight query-related nodes + connecting edges
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.nodes().removeClass('query-highlight');
    cy.edges().removeClass('query-highlight-edge');

    if (highlightNodeIds.size > 0) {
      for (const id of highlightNodeIds) {
        const node = cy.getElementById(id);
        if (node.length > 0) {
          node.addClass('query-highlight');
        }
      }

      // Highlight edges where BOTH endpoints are in the highlight set
      cy.edges().forEach((edge) => {
        const srcId = edge.source().id();
        const tgtId = edge.target().id();
        if (highlightNodeIds.has(srcId) && highlightNodeIds.has(tgtId)) {
          edge.addClass('query-highlight-edge');
        }
      });

      // Dim non-highlighted elements
      cy.nodes().not('.query-highlight').addClass('query-dimmed');
      cy.edges().not('.query-highlight-edge').addClass('query-dimmed-edge');

      // Fit view to all highlighted nodes
      const highlighted = cy.nodes('.query-highlight');
      if (highlighted.length > 0) {
        cy.animate(
          { fit: { eles: highlighted, padding: 60 } },
          { duration: 500 },
        );
      }
    } else {
      cy.nodes().removeClass('query-dimmed');
      cy.edges().removeClass('query-dimmed-edge');
    }
  }, [highlightNodeIds, cyRef]);

  const stylesheet = buildStylesheet(visibleLabels);

  const fullStylesheet = [
    ...stylesheet,
    {
      selector: 'node.search-match',
      style: {
        'border-width': 4,
        'border-color': '#eab308',
        'overlay-color': '#eab308',
        'overlay-opacity': 0.2,
        width: 44,
        height: 44,
      },
    },
    {
      selector: 'node.query-highlight',
      style: {
        'border-width': 4,
        'border-color': '#8b5cf6',
        'overlay-color': '#8b5cf6',
        'overlay-opacity': 0.25,
        width: 48,
        height: 48,
        'z-index': 10,
      },
    },
    {
      selector: 'edge.query-highlight-edge',
      style: {
        width: 3,
        'line-color': '#8b5cf6',
        'target-arrow-color': '#8b5cf6',
        'line-opacity': 1,
        'z-index': 10,
      },
    },
    {
      selector: 'node.query-dimmed',
      style: {
        opacity: 0.2,
      },
    },
    {
      selector: 'edge.query-dimmed-edge',
      style: {
        opacity: 0.1,
      },
    },
  ];

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={fullStylesheet as never}
      layout={LAYOUT_OPTIONS[layout]}
      cy={handleCy}
      style={{ width: '100%', height: '100%' }}
      wheelSensitivity={0.3}
    />
  );
}
