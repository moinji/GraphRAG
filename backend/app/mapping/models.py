"""Pydantic models for YAML domain mapping — R2RML-compatible structure.

Terminology aligned with W3C R2RML:
- TriplesMap  → node mapping (table → node label + properties)
- LogicalTable → source RDB table
- SubjectMap → node label + key template
- PredicateObjectMap → property mappings + relationship mappings
"""

from __future__ import annotations

from pydantic import BaseModel


class LogicalTable(BaseModel):
    """R2RML rr:logicalTable — source RDB table reference."""
    table_name: str


class SubjectMap(BaseModel):
    """R2RML rr:SubjectMap — node label + key template."""
    class_: str  # Neo4j node label (PascalCase). Named class_ to avoid Python keyword.
    template: str = "{id}"  # key pattern for identifier

    model_config = {"populate_by_name": True}

    def model_dump(self, **kwargs):
        d = super().model_dump(**kwargs)
        # Serialize as "class" instead of "class_" for YAML readability
        d["class"] = d.pop("class_")
        return d

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if isinstance(obj, dict) and "class" in obj and "class_" not in obj:
            obj = {**obj, "class_": obj.pop("class")}
        return super().model_validate(obj, **kwargs)


class MappingProperty(BaseModel):
    """A single property mapping (column → graph property)."""
    name: str
    column: str
    datatype: str = "string"
    is_key: bool = False


class JoinCondition(BaseModel):
    """R2RML rr:joinCondition — FK join columns."""
    source_column: str
    target_column: str


class TriplesMapEntry(BaseModel):
    """R2RML TriplesMap — one node type mapping."""
    id: str  # e.g. "TM_Customer"
    logical_table: LogicalTable
    subject_map: SubjectMap
    properties: list[MappingProperty] = []


class RelationshipMapEntry(BaseModel):
    """R2RML RefObjectMap — one relationship mapping."""
    id: str  # e.g. "RM_PLACED"
    type: str  # relationship type name (UPPER_SNAKE)
    source_triples_map: str  # reference to TriplesMapEntry.id
    target_triples_map: str  # reference to TriplesMapEntry.id
    logical_table: LogicalTable
    join_condition: JoinCondition
    derivation: str = "fk_direct"
    properties: list[MappingProperty] = []


class TypeMapping(BaseModel):
    """Type conversion rule for a datatype."""
    neo4j_type: str
    python_type: str = "str"
    format: str | None = None


class MappingMetadata(BaseModel):
    """YAML metadata header."""
    domain: str | None = None
    generated_at: str | None = None
    source_ontology_version: int | None = None
    generator: str = "autograph-f02"


class DomainMappingConfig(BaseModel):
    """Top-level YAML structure — complete domain mapping configuration."""
    version: str = "1.0"
    metadata: MappingMetadata = MappingMetadata()
    triples_maps: list[TriplesMapEntry] = []
    relationship_maps: list[RelationshipMapEntry] = []
    type_mappings: dict[str, TypeMapping] = {}
