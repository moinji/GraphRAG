// Mirrors backend Graph visualization models (app/models/schemas.py)

export interface GraphNode {
  id: string;
  label: string;
  properties: Record<string, string | number | boolean | null>;
  display_name: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  rel_type: string;
  properties: Record<string, string | number | boolean | null>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  truncated: boolean;
}

export interface GraphStats {
  node_counts: Record<string, number>;
  edge_counts: Record<string, number>;
  total_nodes: number;
  total_edges: number;
}
