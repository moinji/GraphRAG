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
  warnings: string[];
  quality_score: number | null;
  detected_domain: string | null;
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

// ── KG Build ────────────────────────────────────────────────────

export interface KGBuildProgress {
  nodes_created: number;
  relationships_created: number;
  duration_seconds: number;
  current_step: string;
  step_number: number;
  total_steps: number;
  error_count: number;
}

// ── Mapping ──────────────────────────────────────────────────────

export interface MappingGenerateResponse {
  yaml_content: string;
  triples_map_count: number;
  relationship_map_count: number;
  validation_warnings: string[];
  version_id: number;
}

export interface MappingPreview {
  version_id: number;
  node_count: number;
  relationship_count: number;
  table_mappings: { table: string; node_label: string; property_count: number }[];
  domain: string | null;
}

export interface KGBuildErrorDetail {
  stage: string;
  message: string;
  detail: string;
}

export interface KGBuildResponse {
  build_job_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  progress: KGBuildProgress | null;
  error: KGBuildErrorDetail | null;
  version_id: number;
  started_at: string | null;
  completed_at: string | null;
}

// ── CSV Import ─────────────────────────────────────────────────

export interface CSVTableSummary {
  table_name: string;
  row_count: number;
  columns: string[];
  warnings: string[];
}

export interface CSVUploadResponse {
  csv_session_id: string;
  tables: CSVTableSummary[];
  errors: string[];
  warnings: string[];
}

// ── Query API ──────────────────────────────────────────────────

export interface DocumentSource {
  document_id: number;
  filename: string;
  chunk_text: string;
  relevance_score: number;
  page_num: number | null;
  chunk_index: number;
}

export interface QueryResponse {
  question: string;
  answer: string;
  cypher: string;
  paths: string[];
  template_id: string;
  route: string;
  matched_by: string;
  error: string | null;
  mode: string;
  subgraph_context: string | null;
  llm_tokens_used: number | null;
  latency_ms: number | null;
  cached: boolean;
  related_node_ids: string[];
  document_sources: DocumentSource[];
}

// ── Document Management (v5.0) ──────────────────────────────────

export interface DocumentInfo {
  document_id: number;
  filename: string;
  file_type: string;
  file_size: number;
  page_count: number;
  chunk_count: number;
  status: 'processing' | 'ready' | 'failed';
  created_at: string;
}

export interface DocumentUploadResponse {
  accepted: { filename: string; size: number; status: string }[];
  errors: string[];
  total_queued: number;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
  total: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  data?: QueryResponse;
  wisdomData?: WisdomResponse;
  streaming?: boolean;
}

// ── DIKW Wisdom ─────────────────────────────────────────────────

export interface DIKWLayer {
  level: 'data' | 'information' | 'knowledge' | 'wisdom';
  title: string;
  content: string;
  evidence: string[];
}

export interface WisdomResponse {
  question: string;
  intent: string;
  dikw_layers: DIKWLayer[];
  summary: string;
  confidence: string;
  action_items: string[];
  related_queries: string[];
  cypher_queries_used: string[];
  latency_ms: number;
  llm_tokens_used: number;
}

// ── OWL ──────────────────────────────────────────────────────────

export interface OWLExportResponse {
  content: string;
  format: string;
  triple_count: number;
  class_count: number;
  property_count: number;
}

export interface SHACLIssue {
  severity: string;
  message: string;
  details: Record<string, string>;
}

export interface SHACLValidationResponse {
  conforms: boolean;
  issue_count: number;
  issues: SHACLIssue[];
  level: string;
}
