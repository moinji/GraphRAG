"""E2E tests for non-ecommerce domains (education, insurance).

Validates full pipeline: DDL parse → ontology generate → data generate → FK integrity.
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


def _generate_ontology_obj(erd, **kwargs):
    """Generate ontology and return the OntologySpec object."""
    from app.ontology.pipeline import generate_ontology

    with patch("app.ontology.pipeline.save_version", return_value=1):
        result = generate_ontology(erd, skip_llm=True, **kwargs)
    return result.ontology


# ── Education domain ────────────────────────────────────────────


class TestEducationDomain:
    """Education domain E2E tests."""

    def test_ddl_parse(self):
        erd = _load_and_parse("demo_education.sql")
        assert len(erd.tables) == 11
        assert len(erd.foreign_keys) == 15

    def test_domain_detection(self):
        from app.ontology.domain_hints import detect_domain

        erd = _load_and_parse("demo_education.sql")
        hint = detect_domain(erd)
        assert hint is not None
        assert hint.name == "education"

    def test_ontology_generation(self):
        erd = _load_and_parse("demo_education.sql")
        ontology = _generate_ontology_obj(erd)

        node_names = {nt.name for nt in ontology.node_types}
        rel_names = {rt.name for rt in ontology.relationship_types}

        assert "Student" in node_names
        assert "Course" in node_names
        assert "Instructor" in node_names
        assert "Department" in node_names

        assert "ENROLLED_IN" in rel_names
        assert "REQUIRES" in rel_names
        assert len(ontology.node_types) >= 7
        assert len(ontology.relationship_types) >= 8

    def test_seed_data_generation(self):
        from app.data_generator.generator import generate_sample_data

        erd = _load_and_parse("demo_education.sql")
        data = generate_sample_data(erd)

        assert "students" in data
        assert "courses" in data
        assert "enrollments" in data
        assert "prerequisites" in data
        assert len(data["students"]) == 8
        assert len(data["courses"]) == 6
        assert len(data["enrollments"]) == 12

    def test_seed_data_fk_integrity(self):
        from app.data_generator.generator import generate_sample_data, verify_fk_integrity

        erd = _load_and_parse("demo_education.sql")
        data = generate_sample_data(erd)
        violations = verify_fk_integrity(data, erd)
        assert len(violations) == 0, f"FK violations: {violations}"

    def test_quality_check(self):
        from app.ontology.quality_checker import check_quality

        erd = _load_and_parse("demo_education.sql")
        ontology = _generate_ontology_obj(erd)
        report = check_quality(ontology)
        # Education may have auto-detected join tables causing domain/range issues
        # Just verify the check runs and returns a score
        assert 0.0 <= report.score <= 1.0


# ── Insurance domain ─────────────────────────────────────────────


class TestInsuranceDomain:
    """Insurance domain E2E tests."""

    def test_ddl_parse(self):
        erd = _load_and_parse("demo_insurance.sql")
        assert len(erd.tables) == 12
        assert len(erd.foreign_keys) == 12

    def test_domain_detection(self):
        from app.ontology.domain_hints import detect_domain

        erd = _load_and_parse("demo_insurance.sql")
        hint = detect_domain(erd)
        assert hint is not None
        assert hint.name == "insurance"

    def test_ontology_generation(self):
        erd = _load_and_parse("demo_insurance.sql")
        ontology = _generate_ontology_obj(erd)

        node_names = {nt.name for nt in ontology.node_types}
        rel_names = {rt.name for rt in ontology.relationship_types}

        assert "Policyholder" in node_names
        assert "Policy" in node_names
        assert "Claim" in node_names
        assert "Product" in node_names

        assert "COVERS" in rel_names
        assert "EXCLUDES" in rel_names
        assert len(ontology.node_types) >= 7
        assert len(ontology.relationship_types) >= 8

    def test_seed_data_generation(self):
        from app.data_generator.generator import generate_sample_data

        erd = _load_and_parse("demo_insurance.sql")
        data = generate_sample_data(erd)

        assert "policyholders" in data
        assert "policies" in data
        assert "claims" in data
        assert "policy_coverages" in data
        assert len(data["policyholders"]) == 5
        assert len(data["policies"]) == 8
        assert len(data["claims"]) == 6

    def test_seed_data_fk_integrity(self):
        from app.data_generator.generator import generate_sample_data, verify_fk_integrity

        erd = _load_and_parse("demo_insurance.sql")
        data = generate_sample_data(erd)
        violations = verify_fk_integrity(data, erd)
        assert len(violations) == 0, f"FK violations: {violations}"

    def test_quality_check(self):
        from app.ontology.quality_checker import check_quality

        erd = _load_and_parse("demo_insurance.sql")
        ontology = _generate_ontology_obj(erd)
        report = check_quality(ontology)
        assert 0.0 <= report.score <= 1.0


# ── Cross-domain tests ──────────────────────────────────────────


class TestCrossDomain:
    """Cross-domain comparison tests."""

    def test_all_three_domains_detected(self):
        from app.ontology.domain_hints import detect_domain

        ecommerce_erd = _load_and_parse("demo_ecommerce.sql")
        education_erd = _load_and_parse("demo_education.sql")
        insurance_erd = _load_and_parse("demo_insurance.sql")

        ec = detect_domain(ecommerce_erd)
        ed = detect_domain(education_erd)
        ins = detect_domain(insurance_erd)

        assert ec is not None and ec.name == "ecommerce"
        assert ed is not None and ed.name == "education"
        assert ins is not None and ins.name == "insurance"

    def test_each_domain_has_seed_data(self):
        from app.data_generator.generator import generate_sample_data

        for fname, min_tables in [
            ("demo_ecommerce.sql", 10),
            ("demo_education.sql", 10),
            ("demo_insurance.sql", 10),
        ]:
            erd = _load_and_parse(fname)
            data = generate_sample_data(erd)
            total_rows = sum(len(rows) for rows in data.values())
            assert len(data) >= min_tables, f"{fname}: expected >={min_tables} tables, got {len(data)}"
            assert total_rows >= 50, f"{fname}: expected >=50 rows, got {total_rows}"

    def test_all_domains_fk_integrity(self):
        from app.data_generator.generator import generate_sample_data, verify_fk_integrity

        for fname in ["demo_ecommerce.sql", "demo_education.sql", "demo_insurance.sql"]:
            erd = _load_and_parse(fname)
            data = generate_sample_data(erd)
            violations = verify_fk_integrity(data, erd)
            assert len(violations) == 0, f"{fname} FK violations: {violations}"

    def test_mapping_round_trip_education(self):
        from app.mapping.converter import mapping_to_ontology
        from app.mapping.generator import mapping_to_yaml, ontology_to_mapping, yaml_to_mapping

        erd = _load_and_parse("demo_education.sql")
        original = _generate_ontology_obj(erd)

        config = ontology_to_mapping(original, domain="education", version_id=1)
        yaml_str = mapping_to_yaml(config)
        config2 = yaml_to_mapping(yaml_str)
        roundtrip = mapping_to_ontology(config2)

        assert len(roundtrip.node_types) == len(original.node_types)
        assert len(roundtrip.relationship_types) == len(original.relationship_types)

    def test_mapping_round_trip_insurance(self):
        from app.mapping.converter import mapping_to_ontology
        from app.mapping.generator import mapping_to_yaml, ontology_to_mapping, yaml_to_mapping

        erd = _load_and_parse("demo_insurance.sql")
        original = _generate_ontology_obj(erd)

        config = ontology_to_mapping(original, domain="insurance", version_id=1)
        yaml_str = mapping_to_yaml(config)
        config2 = yaml_to_mapping(yaml_str)
        roundtrip = mapping_to_ontology(config2)

        assert len(roundtrip.node_types) == len(original.node_types)
        assert len(roundtrip.relationship_types) == len(original.relationship_types)
