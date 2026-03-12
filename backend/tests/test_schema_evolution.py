"""Tests for schema evolution: diff, impact, migration API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.schemas import (
    NodeProperty,
    NodeType,
    OntologySpec,
    RelProperty,
    RelationshipType,
)
from app.schema_evolution.diff import compute_diff


# ── Fixtures ─────────────────────────────────────────────────────


def _make_ontology(
    nodes: list[tuple[str, str, list[tuple[str, str, bool]]]],
    rels: list[tuple[str, str, str, str]] | None = None,
) -> OntologySpec:
    """Quick ontology builder: (name, table, [(prop, type, is_key)])."""
    node_types = []
    for name, table, props in nodes:
        node_types.append(NodeType(
            name=name,
            source_table=table,
            properties=[
                NodeProperty(name=p[0], source_column=p[0], type=p[1], is_key=p[2])
                for p in props
            ],
        ))
    rel_types = []
    if rels:
        for rname, src, tgt, dtable in rels:
            rel_types.append(RelationshipType(
                name=rname,
                source_node=src,
                target_node=tgt,
                data_table=dtable,
                source_key_column=f"{src.lower()}_id",
                target_key_column=f"{tgt.lower()}_id",
            ))
    return OntologySpec(node_types=node_types, relationship_types=rel_types)


@pytest.fixture
def base_ontology():
    return _make_ontology(
        nodes=[
            ("Customer", "customers", [("id", "integer", True), ("name", "string", False)]),
            ("Product", "products", [("id", "integer", True), ("name", "string", False), ("price", "decimal", False)]),
            ("Order", "orders", [("id", "integer", True), ("status", "string", False)]),
        ],
        rels=[
            ("PLACED", "Customer", "Order", "orders"),
            ("CONTAINS", "Order", "Product", "order_items"),
        ],
    )


@pytest.fixture
def target_add_node(base_ontology):
    """Target ontology with added Category node + BELONGS_TO rel."""
    ont = base_ontology.model_copy(deep=True)
    ont.node_types.append(NodeType(
        name="Category",
        source_table="categories",
        properties=[
            NodeProperty(name="id", source_column="id", type="integer", is_key=True),
            NodeProperty(name="name", source_column="name", type="string"),
        ],
    ))
    ont.relationship_types.append(RelationshipType(
        name="BELONGS_TO",
        source_node="Product",
        target_node="Category",
        data_table="products",
        source_key_column="id",
        target_key_column="category_id",
    ))
    return ont


@pytest.fixture
def target_remove_node():
    """Target with Customer and Product only (Order removed)."""
    return _make_ontology(
        nodes=[
            ("Customer", "customers", [("id", "integer", True), ("name", "string", False)]),
            ("Product", "products", [("id", "integer", True), ("name", "string", False), ("price", "decimal", False)]),
        ],
        rels=[],
    )


@pytest.fixture
def target_modify_node(base_ontology):
    """Target with modified Product (added 'description', removed 'price')."""
    ont = base_ontology.model_copy(deep=True)
    product = next(nt for nt in ont.node_types if nt.name == "Product")
    product.properties = [
        NodeProperty(name="id", source_column="id", type="integer", is_key=True),
        NodeProperty(name="name", source_column="name", type="string"),
        NodeProperty(name="description", source_column="description", type="string"),
    ]
    return ont


# ── Diff Tests ───────────────────────────────────────────────────


class TestDiffEngine:
    def test_identical_specs(self, base_ontology):
        diff = compute_diff(base_ontology, base_ontology, 1, 1)
        assert len(diff.node_diffs) == 0
        assert len(diff.relationship_diffs) == 0
        assert diff.summary == "No changes"
        assert not diff.is_breaking

    def test_added_node(self, base_ontology, target_add_node):
        diff = compute_diff(base_ontology, target_add_node, 1, 2)
        added_nodes = [d for d in diff.node_diffs if d.change_type == "added"]
        assert len(added_nodes) == 1
        assert added_nodes[0].name == "Category"
        added_rels = [d for d in diff.relationship_diffs if d.change_type == "added"]
        assert len(added_rels) == 1
        assert added_rels[0].name == "BELONGS_TO"
        assert not diff.is_breaking

    def test_removed_node(self, base_ontology, target_remove_node):
        diff = compute_diff(base_ontology, target_remove_node, 1, 2)
        removed_nodes = [d for d in diff.node_diffs if d.change_type == "removed"]
        assert len(removed_nodes) == 1
        assert removed_nodes[0].name == "Order"
        assert diff.is_breaking

    def test_modified_properties(self, base_ontology, target_modify_node):
        diff = compute_diff(base_ontology, target_modify_node, 1, 2)
        modified = [d for d in diff.node_diffs if d.change_type == "modified"]
        assert len(modified) == 1
        assert modified[0].name == "Product"
        prop_names = {pc.name for pc in modified[0].property_changes}
        assert "price" in prop_names  # removed
        assert "description" in prop_names  # added

    def test_endpoint_change_is_breaking(self, base_ontology):
        target = base_ontology.model_copy(deep=True)
        # Change PLACED source from Customer to Product
        placed = next(rt for rt in target.relationship_types if rt.name == "PLACED")
        placed.source_node = "Product"
        diff = compute_diff(base_ontology, target, 1, 2)
        modified_rels = [d for d in diff.relationship_diffs if d.change_type == "modified"]
        assert len(modified_rels) == 1
        assert modified_rels[0].endpoint_changed
        assert diff.is_breaking

    def test_summary_format(self, base_ontology, target_add_node):
        diff = compute_diff(base_ontology, target_add_node, 1, 2)
        assert "nodes +1" in diff.summary
        assert "rels +1" in diff.summary

    def test_rel_property_change(self):
        base = _make_ontology(
            nodes=[("A", "a", [("id", "integer", True)])],
            rels=[("LINKS", "A", "A", "links")],
        )
        base.relationship_types[0].properties = [
            RelProperty(name="weight", source_column="weight", type="integer"),
        ]
        target = base.model_copy(deep=True)
        target.relationship_types[0].properties = [
            RelProperty(name="weight", source_column="weight", type="float"),
        ]
        diff = compute_diff(base, target, 1, 2)
        assert len(diff.relationship_diffs) == 1
        assert diff.relationship_diffs[0].property_changes[0].change_type == "modified"

    def test_mixed_changes(self, base_ontology, target_remove_node):
        """Remove Order, keep Customer/Product — rels PLACED and CONTAINS removed."""
        diff = compute_diff(base_ontology, target_remove_node, 1, 2)
        assert diff.is_breaking
        removed_rels = [d for d in diff.relationship_diffs if d.change_type == "removed"]
        assert len(removed_rels) == 2


# ── API Tests ────────────────────────────────────────────────────


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def _mock_get_version(ontology: OntologySpec, version_id: int = 1):
    return {
        "id": version_id,
        "erd_hash": "abc",
        "ontology_json": ontology.model_dump(),
        "eval_json": None,
        "status": "approved",
        "tenant_id": "_default_",
    }


class TestDiffAPI:
    @patch("app.db.pg_client.get_version")
    def test_diff_endpoint(self, mock_get, client, base_ontology, target_add_node):
        mock_get.side_effect = lambda vid, **kw: (
            _mock_get_version(base_ontology, 1) if vid == 1
            else _mock_get_version(target_add_node, 2)
        )
        resp = client.post("/api/v1/ontology/diff?base_version_id=1&target_version_id=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "node_diffs" in data
        assert "summary" in data

    @patch("app.db.pg_client.get_version")
    def test_diff_version_not_found(self, mock_get, client):
        mock_get.return_value = None
        resp = client.post("/api/v1/ontology/diff?base_version_id=999&target_version_id=1")
        assert resp.status_code == 404


class TestMigrationAPI:
    @patch("app.db.pg_client.get_version")
    def test_migrate_returns_202(self, mock_get, client, base_ontology, target_add_node):
        mock_get.side_effect = lambda vid, **kw: (
            _mock_get_version(base_ontology, 1) if vid == 1
            else _mock_get_version(target_add_node, 2)
        )
        resp = client.post("/api/v1/kg/migrate", json={
            "base_version_id": 1,
            "target_version_id": 2,
            "erd": {"tables": [], "foreign_keys": []},
            "dry_run": True,
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert data["migration_job_id"].startswith("mig-")

    def test_migration_job_not_found(self, client):
        resp = client.get("/api/v1/kg/migrate/nonexistent")
        assert resp.status_code == 404


# ── Cross-domain Diff Tests ──────────────────────────────────────


class TestCrossDomainDiff:
    def test_ecommerce_to_education_diff(self):
        """Complete schema change should show all nodes as added/removed."""
        ecom = _make_ontology(
            nodes=[("Customer", "customers", [("id", "integer", True)])],
            rels=[],
        )
        edu = _make_ontology(
            nodes=[("Student", "students", [("id", "integer", True)])],
            rels=[],
        )
        diff = compute_diff(ecom, edu, 1, 2)
        assert any(d.name == "Customer" and d.change_type == "removed" for d in diff.node_diffs)
        assert any(d.name == "Student" and d.change_type == "added" for d in diff.node_diffs)
        assert diff.is_breaking

    def test_empty_to_full(self, base_ontology):
        """From empty to full ontology — all additions."""
        empty = OntologySpec(node_types=[], relationship_types=[])
        diff = compute_diff(empty, base_ontology, 0, 1)
        assert all(d.change_type == "added" for d in diff.node_diffs)
        assert all(d.change_type == "added" for d in diff.relationship_diffs)
        assert not diff.is_breaking

    def test_full_to_empty(self, base_ontology):
        """From full to empty — all removals, breaking."""
        empty = OntologySpec(node_types=[], relationship_types=[])
        diff = compute_diff(base_ontology, empty, 1, 0)
        assert all(d.change_type == "removed" for d in diff.node_diffs)
        assert diff.is_breaking
