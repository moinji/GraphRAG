"""YAML mapping layer tests — 20 cases.

Covers: round-trip, generation accuracy, validation, API.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.mapping.converter import mapping_to_ontology
from app.mapping.generator import mapping_to_yaml, ontology_to_mapping, yaml_to_mapping
from app.mapping.validator import validate_mapping
from app.mapping.models import (
    DomainMappingConfig,
    JoinCondition,
    LogicalTable,
    MappingProperty,
    RelationshipMapEntry,
    SubjectMap,
    TriplesMapEntry,
)
from app.models.schemas import (
    ColumnInfo,
    ERDSchema,
    ForeignKey,
    NodeProperty,
    NodeType,
    OntologySpec,
    RelProperty,
    RelationshipType,
    TableInfo,
)
from app.ontology.fk_rule_engine import build_ontology


# ════════════════════════════════════════════════════════════════════
#  Round-trip Tests (1–5)
# ════════════════════════════════════════════════════════════════════


def test_roundtrip_ecommerce(ecommerce_erd: ERDSchema):
    """#1: E-commerce OntologySpec → YAML → OntologySpec preserves all data."""
    original = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(original)
    yaml_str = mapping_to_yaml(config)
    restored_config = yaml_to_mapping(yaml_str)
    restored = mapping_to_ontology(restored_config)

    assert len(restored.node_types) == len(original.node_types)
    assert len(restored.relationship_types) == len(original.relationship_types)

    orig_nodes = {n.name for n in original.node_types}
    rest_nodes = {n.name for n in restored.node_types}
    assert orig_nodes == rest_nodes

    orig_rels = {r.name for r in original.relationship_types}
    rest_rels = {r.name for r in restored.relationship_types}
    assert orig_rels == rest_rels


def test_roundtrip_education():
    """#2: Education domain round-trip."""
    erd = ERDSchema(
        tables=[
            TableInfo(name="students", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="name", data_type="VARCHAR"),
            ], primary_key="id"),
            TableInfo(name="courses", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="title", data_type="VARCHAR"),
            ], primary_key="id"),
        ],
        foreign_keys=[],
    )
    original = build_ontology(erd)
    config = ontology_to_mapping(original, domain="education")
    yaml_str = mapping_to_yaml(config)
    restored = mapping_to_ontology(yaml_to_mapping(yaml_str))
    assert len(restored.node_types) == len(original.node_types)
    assert {n.name for n in restored.node_types} == {n.name for n in original.node_types}


def test_roundtrip_empty():
    """#3: Empty ontology round-trip."""
    original = OntologySpec(node_types=[], relationship_types=[])
    config = ontology_to_mapping(original)
    yaml_str = mapping_to_yaml(config)
    restored = mapping_to_ontology(yaml_to_mapping(yaml_str))
    assert len(restored.node_types) == 0
    assert len(restored.relationship_types) == 0


def test_roundtrip_self_referential():
    """#4: Self-referential relationship (PARENT_OF) preserved."""
    original = OntologySpec(
        node_types=[
            NodeType(name="Category", source_table="categories", properties=[
                NodeProperty(name="id", source_column="id", type="integer", is_key=True),
            ]),
        ],
        relationship_types=[
            RelationshipType(
                name="PARENT_OF", source_node="Category", target_node="Category",
                data_table="categories", source_key_column="parent_id",
                target_key_column="id", derivation="fk_direct",
            ),
        ],
    )
    config = ontology_to_mapping(original)
    restored = mapping_to_ontology(yaml_to_mapping(mapping_to_yaml(config)))
    rel = restored.relationship_types[0]
    assert rel.name == "PARENT_OF"
    assert rel.source_node == "Category"
    assert rel.target_node == "Category"


def test_roundtrip_properties_preserved(ecommerce_erd: ERDSchema):
    """#5: Node and relationship properties round-trip correctly."""
    original = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(original)
    restored = mapping_to_ontology(yaml_to_mapping(mapping_to_yaml(config)))

    # Check CONTAINS relationship properties
    orig_contains = next(r for r in original.relationship_types if r.name == "CONTAINS")
    rest_contains = next(r for r in restored.relationship_types if r.name == "CONTAINS")
    assert {p.name for p in orig_contains.properties} == {p.name for p in rest_contains.properties}

    # Check node property count
    for orig_nt in original.node_types:
        rest_nt = next(n for n in restored.node_types if n.name == orig_nt.name)
        assert len(rest_nt.properties) == len(orig_nt.properties)


# ════════════════════════════════════════════════════════════════════
#  YAML Generation Accuracy (6–10)
# ════════════════════════════════════════════════════════════════════


def test_gen_triples_map_count(ecommerce_erd: ERDSchema):
    """#6: E-commerce generates exactly 9 TriplesMap entries."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    assert len(config.triples_maps) == 9


def test_gen_relationship_map_count(ecommerce_erd: ERDSchema):
    """#7: E-commerce generates exactly 12 RelationshipMap entries."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    assert len(config.relationship_maps) == 12


def test_gen_is_key_matches(ecommerce_erd: ERDSchema):
    """#8: is_key properties in YAML match OntologySpec."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)

    for tm in config.triples_maps:
        # Find corresponding NodeType
        nt = next(n for n in ontology.node_types if n.name == tm.subject_map.class_)
        yaml_keys = {p.name for p in tm.properties if p.is_key}
        onto_keys = {p.name for p in nt.properties if p.is_key}
        assert yaml_keys == onto_keys, f"{tm.id}: key mismatch"


def test_gen_join_table_properties(ecommerce_erd: ERDSchema):
    """#9: CONTAINS relationship has quantity + unit_price properties."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    contains = next(rm for rm in config.relationship_maps if rm.type == "CONTAINS")
    prop_names = {p.name for p in contains.properties}
    assert "quantity" in prop_names
    assert "unit_price" in prop_names


def test_gen_derivation_counts(ecommerce_erd: ERDSchema):
    """#10: 9 fk_direct + 3 fk_join_table derivations in YAML."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    direct = [rm for rm in config.relationship_maps if rm.derivation == "fk_direct"]
    join = [rm for rm in config.relationship_maps if rm.derivation == "fk_join_table"]
    assert len(direct) == 9
    assert len(join) == 3


# ════════════════════════════════════════════════════════════════════
#  YAML Serialization (11–13)
# ════════════════════════════════════════════════════════════════════


def test_yaml_contains_version(ecommerce_erd: ERDSchema):
    """#11: YAML output contains version field."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    yaml_str = mapping_to_yaml(config)
    assert "version: '1.0'" in yaml_str or 'version: "1.0"' in yaml_str


def test_yaml_contains_metadata_domain():
    """#12: YAML metadata includes domain when specified."""
    ontology = OntologySpec(node_types=[], relationship_types=[])
    config = ontology_to_mapping(ontology, domain="insurance")
    yaml_str = mapping_to_yaml(config)
    assert "insurance" in yaml_str


def test_yaml_parseable_back(ecommerce_erd: ERDSchema):
    """#13: Generated YAML is valid and parseable."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    yaml_str = mapping_to_yaml(config)
    # Should not raise
    restored = yaml_to_mapping(yaml_str)
    assert isinstance(restored, DomainMappingConfig)


# ════════════════════════════════════════════════════════════════════
#  Validation Tests (14–17)
# ════════════════════════════════════════════════════════════════════


def test_validate_invalid_source_ref():
    """#14: Non-existent source_triples_map reference → error."""
    config = DomainMappingConfig(
        triples_maps=[
            TriplesMapEntry(
                id="TM_A",
                logical_table=LogicalTable(table_name="a"),
                subject_map=SubjectMap(class_="A"),
                properties=[MappingProperty(name="id", column="id", is_key=True)],
            ),
        ],
        relationship_maps=[
            RelationshipMapEntry(
                id="RM_TEST",
                type="TEST",
                source_triples_map="TM_NONEXISTENT",
                target_triples_map="TM_A",
                logical_table=LogicalTable(table_name="a"),
                join_condition=JoinCondition(source_column="id", target_column="id"),
            ),
        ],
    )
    errors = validate_mapping(config)
    assert any("non-existent" in e for e in errors)


def test_validate_duplicate_tm_id():
    """#15: Duplicate TriplesMap ID → error."""
    config = DomainMappingConfig(
        triples_maps=[
            TriplesMapEntry(
                id="TM_A",
                logical_table=LogicalTable(table_name="a"),
                subject_map=SubjectMap(class_="A"),
                properties=[MappingProperty(name="id", column="id", is_key=True)],
            ),
            TriplesMapEntry(
                id="TM_A",
                logical_table=LogicalTable(table_name="b"),
                subject_map=SubjectMap(class_="B"),
                properties=[MappingProperty(name="id", column="id", is_key=True)],
            ),
        ],
    )
    errors = validate_mapping(config)
    assert any("Duplicate TriplesMap" in e for e in errors)


def test_validate_no_key_warning():
    """#16: TriplesMap without is_key property → warning."""
    config = DomainMappingConfig(
        triples_maps=[
            TriplesMapEntry(
                id="TM_A",
                logical_table=LogicalTable(table_name="a"),
                subject_map=SubjectMap(class_="A"),
                properties=[MappingProperty(name="id", column="id", is_key=False)],
            ),
        ],
    )
    errors = validate_mapping(config)
    assert any("no is_key" in e for e in errors)


def test_validate_clean_config(ecommerce_erd: ERDSchema):
    """#17: Valid e-commerce config has no validation errors."""
    ontology = build_ontology(ecommerce_erd)
    config = ontology_to_mapping(ontology)
    errors = validate_mapping(config)
    # May have warnings (e.g. unknown datatype) but no critical errors
    critical = [e for e in errors if "non-existent" in e or "Duplicate" in e]
    assert len(critical) == 0


# ════════════════════════════════════════════════════════════════════
#  API Tests (18–20)
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _mock_version_row(ontology: OntologySpec, version_id: int = 1) -> dict:
    return {
        "id": version_id,
        "erd_hash": "test",
        "ontology_json": ontology.model_dump(),
        "eval_json": None,
        "status": "approved",
        "created_at": "2026-01-01",
    }


@pytest.mark.anyio
async def test_api_generate_mapping(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#18: POST /api/v1/mapping/generate → 200 + YAML."""
    ontology = build_ontology(ecommerce_erd)
    mock_row = _mock_version_row(ontology)

    with patch("app.routers.mapping.get_version", return_value=mock_row):
        resp = await api_client.post(
            "/api/v1/mapping/generate",
            json={"version_id": 1},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "yaml_content" in data
    assert data["triples_map_count"] == 9
    assert data["relationship_map_count"] == 12


@pytest.mark.anyio
async def test_api_get_mapping(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#19: GET /api/v1/mapping/{version_id} → auto-generates if not stored."""
    ontology = build_ontology(ecommerce_erd)
    mock_row = _mock_version_row(ontology)

    with patch("app.routers.mapping.get_version", return_value=mock_row):
        resp = await api_client.get("/api/v1/mapping/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["triples_map_count"] == 9


@pytest.mark.anyio
async def test_api_get_mapping_preview(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#20: GET /api/v1/mapping/{version_id}/preview → summary info."""
    ontology = build_ontology(ecommerce_erd)
    mock_row = _mock_version_row(ontology)

    with patch("app.routers.mapping.get_version", return_value=mock_row):
        resp = await api_client.get("/api/v1/mapping/1/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 9
    assert data["relationship_count"] == 12
    assert len(data["table_mappings"]) == 9
