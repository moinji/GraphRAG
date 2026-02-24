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


# ── Query Result ───────────────────────────────────────────────────

class QueryResult(BaseModel):
    question: str
    answer: str
    cypher: str
    paths: list[str] = []
    template_id: str = ""
