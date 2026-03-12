"""Real-world data validation tests — Korean DDL, stress-test (30 tables), bootcamp.

Validates that the full pipeline handles:
1. Korean table/column names (한국어 DDL)
2. Large schemas (30 tables, complex FKs)
3. Non-standard education domain (bootcamp)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas"


def _load_and_parse(filename: str):
    from app.ddl_parser.parser import parse_ddl

    path = EXAMPLES_DIR / filename
    ddl = path.read_text(encoding="utf-8")
    return parse_ddl(ddl)


def _generate_ontology(erd):
    from app.ontology.pipeline import generate_ontology

    with patch("app.ontology.pipeline.save_version", return_value=1):
        result = generate_ontology(erd, skip_llm=True)
    return result.ontology


def _generate_data_and_check(erd, ontology):
    from app.data_generator.generator import generate_sample_data, verify_fk_integrity

    data = generate_sample_data(erd)
    violations = verify_fk_integrity(data, erd)
    return data, violations


# ── Korean bookstore (한국어 DDL) ────────────────────────────────


class TestKoreanBookstore:
    """Korean-language DDL with 한글 table/column names."""

    def test_ddl_parse(self):
        erd = _load_and_parse("demo_korean.sql")
        table_names = {t.name for t in erd.tables}
        assert len(erd.tables) == 9
        assert "회원" in table_names
        assert "책" in table_names
        assert "주문" in table_names

    def test_fk_parse(self):
        erd = _load_and_parse("demo_korean.sql")
        assert len(erd.foreign_keys) == 9

    def test_ontology_generation(self):
        erd = _load_and_parse("demo_korean.sql")
        ontology = _generate_ontology(erd)

        node_names = {nt.name for nt in ontology.node_types}
        assert len(ontology.node_types) >= 4  # at least 회원, 책, 작가, 장르
        assert len(ontology.relationship_types) >= 3

    def test_join_table_detection(self):
        """책_작가 and 책_장르 should become relationships, not nodes."""
        erd = _load_and_parse("demo_korean.sql")
        ontology = _generate_ontology(erd)

        node_names = {nt.name for nt in ontology.node_types}
        # Join tables should NOT appear as nodes
        assert "책_작가" not in node_names
        assert "책_장르" not in node_names

    def test_data_generation(self):
        erd = _load_and_parse("demo_korean.sql")
        ontology = _generate_ontology(erd)
        data, violations = _generate_data_and_check(erd, ontology)

        assert len(data) > 0, "Should generate data for at least some tables"

    def test_fk_integrity(self):
        erd = _load_and_parse("demo_korean.sql")
        ontology = _generate_ontology(erd)
        data, violations = _generate_data_and_check(erd, ontology)

        assert violations is None or len(violations) == 0, f"FK violations: {violations}"


# ── Stress test (30 tables, Korean) ────────────────────────────


class TestStressTest30Tables:
    """30-table university schema — validates parser & ontology at scale."""

    def test_ddl_parse(self):
        erd = _load_and_parse("stress_test.sql")
        assert len(erd.tables) >= 30  # 30+ tables in stress test

    def test_fk_count(self):
        erd = _load_and_parse("stress_test.sql")
        assert len(erd.foreign_keys) >= 20  # many inter-table refs

    def test_ontology_generation(self):
        erd = _load_and_parse("stress_test.sql")
        ontology = _generate_ontology(erd)

        # Should produce meaningful node types (not all 30 — join tables removed)
        assert len(ontology.node_types) >= 15
        assert len(ontology.relationship_types) >= 10

    def test_no_duplicate_nodes(self):
        erd = _load_and_parse("stress_test.sql")
        ontology = _generate_ontology(erd)

        node_names = [nt.name for nt in ontology.node_types]
        assert len(node_names) == len(set(node_names)), "Duplicate node types found"

    def test_relationship_count(self):
        """30-table schema should produce many relationships."""
        erd = _load_and_parse("stress_test.sql")
        ontology = _generate_ontology(erd)

        assert len(ontology.relationship_types) >= 10

    def test_data_generation(self):
        erd = _load_and_parse("stress_test.sql")
        ontology = _generate_ontology(erd)
        data, violations = _generate_data_and_check(erd, ontology)

        assert len(data) > 0, "Should generate data for at least some tables"


# ── Bootcamp (English education domain) ─────────────────────────


class TestBootcamp:
    """Developer bootcamp — English education-adjacent schema."""

    def test_ddl_parse(self):
        erd = _load_and_parse("bootcamp_ddl.sql")
        assert len(erd.tables) == 10

    def test_fk_count(self):
        erd = _load_and_parse("bootcamp_ddl.sql")
        assert len(erd.foreign_keys) >= 8

    def test_ontology_generation(self):
        erd = _load_and_parse("bootcamp_ddl.sql")
        ontology = _generate_ontology(erd)

        node_names = {nt.name for nt in ontology.node_types}
        assert "Student" in node_names or "Students" in node_names or any("student" in n.lower() for n in node_names)
        assert "Course" in node_names or "Courses" in node_names or any("course" in n.lower() for n in node_names)

    def test_data_generation_and_fk_integrity(self):
        erd = _load_and_parse("bootcamp_ddl.sql")
        ontology = _generate_ontology(erd)
        data, violations = _generate_data_and_check(erd, ontology)

        assert len(data) > 0
        assert violations is None or len(violations) == 0, f"FK violations: {violations}"


# ── Cross-schema pipeline validation ────────────────────────────


@pytest.mark.parametrize("filename", [
    "demo_korean.sql",
    "stress_test.sql",
    "bootcamp_ddl.sql",
])
def test_full_pipeline_roundtrip(filename):
    """Every schema should parse → ontology → quality check with score > 0."""
    from app.ontology.quality_checker import check_quality

    erd = _load_and_parse(filename)
    ontology = _generate_ontology(erd)
    report = check_quality(ontology)

    # Quality score should be positive (0.0–1.0)
    assert report.score > 0, f"{filename}: quality score is 0"
    assert len(ontology.node_types) >= 3, f"{filename}: too few node types"
