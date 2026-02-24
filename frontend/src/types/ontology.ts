// Mirrors backend Pydantic models (app/models/schemas.py)

// ── DDL Parser output ────────────────────────────────────────────

export interface ColumnInfo {
  name: string;
  data_type: string;
  nullable: boolean;
  is_primary_key: boolean;
}

export interface ForeignKey {
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
  primary_key: string | null;
}

export interface ERDSchema {
  tables: TableInfo[];
  foreign_keys: ForeignKey[];
}

// ── Ontology Spec ────────────────────────────────────────────────

export interface NodeProperty {
  name: string;
  source_column: string;
  type: string;
  is_key: boolean;
}

export interface NodeType {
  name: string;
  source_table: string;
  properties: NodeProperty[];
}

export interface RelProperty {
  name: string;
  source_column: string;
  type: string;
}

export interface RelationshipType {
  name: string;
  source_node: string;
  target_node: string;
  data_table: string;
  source_key_column: string;
  target_key_column: string;
  properties: RelProperty[];
  derivation: string;
}

export interface OntologySpec {
  node_types: NodeType[];
  relationship_types: RelationshipType[];
}

// ── Ontology API ─────────────────────────────────────────────────

export interface LLMEnrichmentDiff {
  field: string;
  before: string | null;
  after: string | null;
  reason: string;
}

export interface EvalMetrics {
  critical_error_rate: number;
  fk_relationship_coverage: number;
  direction_accuracy: number;
  llm_adoption_rate: number | null;
  node_count_generated: number;
  node_count_golden: number;
  relationship_count_generated: number;
  relationship_count_golden: number;
}

export interface OntologyGenerateResponse {
  ontology: OntologySpec;
  eval_report: EvalMetrics | null;
  llm_diffs: LLMEnrichmentDiff[];
  version_id: number | null;
  stage: string;
}

// ── Version API ──────────────────────────────────────────────────

export interface OntologyVersionResponse {
  version_id: number;
  erd_hash: string;
  ontology: OntologySpec;
  eval_report: EvalMetrics | null;
  status: string;
  created_at: string | null;
}

export interface OntologyUpdateResponse {
  version_id: number;
  status: string;
  updated: boolean;
}

export interface OntologyApproveResponse {
  version_id: number;
  status: string;
}
