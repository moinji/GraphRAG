"""Shared Pydantic models for the entire pipeline."""

from __future__ import annotations

from pydantic import BaseModel


# ── DDL Parser output ──────────────────────────────────────────────

class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False


class ForeignKey(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    primary_key: str | None = None
    primary_keys: list[str] = []  # composite PK support


class ERDSchema(BaseModel):
    tables: list[TableInfo]
    foreign_keys: list[ForeignKey]


# ── Ontology Spec ──────────────────────────────────────────────────

class NodeProperty(BaseModel):
    name: str
    source_column: str
    type: str = "string"
    is_key: bool = False


class NodeType(BaseModel):
    name: str          # PascalCase label
    source_table: str
    properties: list[NodeProperty]


class RelProperty(BaseModel):
    name: str
    source_column: str
    type: str = "string"


class RelationshipType(BaseModel):
    name: str              # UPPER_SNAKE relationship type
    source_node: str       # source node label
    target_node: str       # target node label
    data_table: str        # table whose rows provide the data
    source_key_column: str # column in data_table → matches source node id
    target_key_column: str # column in data_table → matches target node id
    properties: list[RelProperty] = []
    derivation: str = "fk_direct"


class OntologySpec(BaseModel):
    node_types: list[NodeType]
    relationship_types: list[RelationshipType]


# ── Ontology API ───────────────────────────────────────────────────

class OntologyGenerateRequest(BaseModel):
    erd: ERDSchema
    skip_llm: bool = False


class LLMEnrichmentDiff(BaseModel):
    field: str
    before: str | None
    after: str | None
    reason: str = ""


class EvalMetrics(BaseModel):
    critical_error_rate: float
    fk_relationship_coverage: float
    direction_accuracy: float
    llm_adoption_rate: float | None = None
    node_count_generated: int
    node_count_golden: int
    relationship_count_generated: int
    relationship_count_golden: int


class OntologyGenerateResponse(BaseModel):
    ontology: OntologySpec
    eval_report: EvalMetrics | None = None
    llm_diffs: list[LLMEnrichmentDiff] = []
    version_id: int | None = None
    stage: str = "fk_only"
    warnings: list[str] = []


# ── Ontology Version API ──────────────────────────────────────────

class OntologyVersionResponse(BaseModel):
    version_id: int
    erd_hash: str
    ontology: OntologySpec
    eval_report: EvalMetrics | None = None
    status: str = "draft"
    created_at: str | None = None


class OntologyUpdateRequest(BaseModel):
    ontology: OntologySpec


class OntologyUpdateResponse(BaseModel):
    version_id: int
    status: str
    updated: bool


class OntologyApproveResponse(BaseModel):
    version_id: int
    status: str


# ── KG Build Job ──────────────────────────────────────────────────

class KGBuildRequest(BaseModel):
    version_id: int
    erd: ERDSchema
    csv_session_id: str | None = None


class KGBuildProgress(BaseModel):
    nodes_created: int = 0
    relationships_created: int = 0
    duration_seconds: float = 0.0
    current_step: str = ""  # data_generation | fk_verification | neo4j_load | completed
    step_number: int = 0    # 1-4
    total_steps: int = 4


class KGBuildErrorDetail(BaseModel):
    stage: str
    message: str
    detail: str = ""


class KGBuildResponse(BaseModel):
    build_job_id: str
    status: str  # queued | running | succeeded | failed
    progress: KGBuildProgress | None = None
    error: KGBuildErrorDetail | None = None
    version_id: int
    started_at: str | None = None
    completed_at: str | None = None


# ── CSV Import ───────────────────────────────────────────────────

class CSVTableSummary(BaseModel):
    table_name: str
    row_count: int
    columns: list[str]
    warnings: list[str] = []


class CSVUploadResponse(BaseModel):
    csv_session_id: str
    tables: list[CSVTableSummary]
    errors: list[str] = []
    warnings: list[str] = []


# ── Query Result (v0 demo) ─────────────────────────────────────────

class QueryResult(BaseModel):
    question: str
    answer: str
    cypher: str
    paths: list[str] = []
    template_id: str = ""


# ── Query API (v0.5 hybrid router) ────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    mode: str = "a"  # "a" | "b"


class QueryResponse(BaseModel):
    question: str
    answer: str
    cypher: str
    paths: list[str] = []
    template_id: str = ""
    route: str = ""           # cypher_traverse | cypher_agg | unsupported
    matched_by: str = ""      # rule | llm | none
    error: str | None = None
    mode: str = "a"
    subgraph_context: str | None = None
    llm_tokens_used: int | None = None
    latency_ms: int | None = None
    cached: bool = False
    related_node_ids: list[str] = []


# ── QA Evaluation ────────────────────────────────────────────────

class QAGoldenPair(BaseModel):
    id: str
    question: str
    category: str                    # traverse | aggregate | comparison | unsupported
    expected_keywords: list[str]
    expected_entities: list[str]
    difficulty: str = "medium"


class QASingleResult(BaseModel):
    qa_id: str
    mode: str
    question: str
    answer: str
    keyword_score: float
    entity_score: float
    latency_ms: int
    llm_tokens: int = 0
    success: bool
    error: str | None = None


class QAComparisonReport(BaseModel):
    total_pairs: int
    a_results: list[QASingleResult]
    b_results: list[QASingleResult]
    a_success_count: int
    b_success_count: int
    a_avg_latency_ms: float
    b_avg_latency_ms: float
    a_avg_keyword_score: float
    b_avg_keyword_score: float
    b_total_tokens: int
    b_estimated_cost_usd: float
    recommendation: str


# ── Graph Visualization ─────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    properties: dict[str, str | int | float | bool | None] = {}
    display_name: str = ""


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    rel_type: str
    properties: dict[str, str | int | float | bool | None] = {}


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int = 0
    total_edges: int = 0
    truncated: bool = False


class GraphStats(BaseModel):
    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    total_nodes: int = 0
    total_edges: int = 0


class GraphResetResponse(BaseModel):
    deleted_nodes: int = 0
    deleted_edges: int = 0


# ── Health Check ────────────────────────────────────────────────

class ServiceHealth(BaseModel):
    status: str
    latency_ms: float | None = None
    detail: str | None = None


class HealthCheckResponse(BaseModel):
    status: str
    neo4j: ServiceHealth
    postgres: ServiceHealth


# ── DIKW Wisdom ────────────────────────────────────────────────

class DIKWLayer(BaseModel):
    level: str               # "data" | "information" | "knowledge" | "wisdom"
    title: str
    content: str
    evidence: list[str] = []


class WisdomRequest(BaseModel):
    question: str


class WisdomResponse(BaseModel):
    question: str
    intent: str              # pattern | causal | recommendation | what_if | dikw_trace
    dikw_layers: list[DIKWLayer]
    summary: str
    confidence: str          # high | medium | low
    action_items: list[str] = []
    related_queries: list[str] = []
    cypher_queries_used: list[str] = []
    latency_ms: int = 0
    llm_tokens_used: int = 0
