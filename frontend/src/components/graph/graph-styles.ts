/** Color map for node labels. */
export const NODE_COLORS: Record<string, string> = {
  Customer: '#6366f1',    // indigo
  Product: '#10b981',     // emerald
  Order: '#f59e0b',       // amber
  OrderItem: '#f97316',   // orange
  Category: '#8b5cf6',    // violet
  Review: '#ec4899',      // pink
  Supplier: '#06b6d4',    // cyan
  Payment: '#14b8a6',     // teal
  Shipment: '#3b82f6',    // blue
  Address: '#64748b',     // slate
  Inventory: '#84cc16',   // lime
  Promotion: '#ef4444',   // red
};

const DEFAULT_NODE_COLOR = '#94a3b8'; // slate-400

export function getNodeColor(label: string): string {
  return NODE_COLORS[label] ?? DEFAULT_NODE_COLOR;
}

/** Build a Cytoscape stylesheet for the graph. */
export function buildStylesheet(_activeLabels: Set<string>) {
  const nodeStyles: Array<{ selector: string; style: Record<string, unknown> }> = [
    {
      selector: 'node',
      style: {
        label: 'data(display_name)',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'font-size': '11px',
        'text-margin-y': 6,
        'min-zoomed-font-size': 10,
        color: '#374151',
        'text-outline-color': '#ffffff',
        'text-outline-width': 2,
        width: 36,
        height: 36,
        'border-width': 2,
        'border-color': '#e5e7eb',
        'background-color': DEFAULT_NODE_COLOR,
        'overlay-padding': 4,
      },
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 3,
        'border-color': '#1d4ed8',
        'overlay-color': '#3b82f6',
        'overlay-opacity': 0.15,
      },
    },
  ];

  // Per-label color styles
  for (const [label, color] of Object.entries(NODE_COLORS)) {
    nodeStyles.push({
      selector: `node[label="${label}"]`,
      style: {
        'background-color': color,
      },
    });
  }

  const edgeStyles: Array<{ selector: string; style: Record<string, unknown> }> = [
    {
      selector: 'edge',
      style: {
        width: 1.5,
        'line-color': '#cbd5e1',
        'target-arrow-color': '#cbd5e1',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
        'curve-style': 'bezier',
        label: 'data(rel_type)',
        'font-size': '9px',
        'text-rotation': 'autorotate',
        'text-margin-y': -8,
        'min-zoomed-font-size': 12,
        color: '#9ca3af',
        'text-outline-color': '#ffffff',
        'text-outline-width': 1.5,
      },
    },
    {
      selector: 'edge:selected',
      style: {
        width: 2.5,
        'line-color': '#3b82f6',
        'target-arrow-color': '#3b82f6',
      },
    },
  ];

  return [...nodeStyles, ...edgeStyles];
}
