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

  // Highlight query-related nodes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.nodes().removeClass('query-highlight');
    if (highlightNodeIds.size > 0) {
      for (const id of highlightNodeIds) {
        const node = cy.getElementById(id);
        if (node.length > 0) {
          node.addClass('query-highlight');
        }
      }
      // Fit view to all highlighted nodes
      const highlighted = cy.nodes('.query-highlight');
      if (highlighted.length > 0) {
        cy.animate(
          { fit: { eles: highlighted, padding: 60 } },
          { duration: 500 },
        );
      }
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
        'overlay-opacity': 0.2,
        width: 48,
        height: 48,
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
