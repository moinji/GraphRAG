"""Multi-domain DDL parsing + ontology generation tests — 12 cases."""

from __future__ import annotations

import pytest

from app.ddl_parser.parser import parse_ddl
from app.ontology.fk_rule_engine import build_ontology


# ════════════════════════════════════════════════════════════════════
#  Accounting Domain (10 tables, 18 FKs)
# ════════════════════════════════════════════════════════════════════


def test_accounting_table_count(accounting_ddl: str):
    """#1: Accounting DDL parses 10 tables."""
    erd = parse_ddl(accounting_ddl)
    assert len(erd.tables) == 10


def test_accounting_fk_count(accounting_ddl: str):
    """#2: Accounting DDL has 18 FK constraints."""
    erd = parse_ddl(accounting_ddl)
    assert len(erd.foreign_keys) == 18


def test_accounting_ontology(accounting_ddl: str):
    """#3: Accounting ontology generates correct node/rel counts."""
    erd = parse_ddl(accounting_ddl)
    onto = build_ontology(erd)
    names = {nt.name for nt in onto.node_types}
    assert "Employee" in names
    assert "Account" in names
    assert "JournalEntry" in names
    assert len(onto.node_types) == 10
    assert len(onto.relationship_types) >= 12


# ════════════════════════════════════════════════════════════════════
#  HR Domain (11 tables, 16 FKs)
# ════════════════════════════════════════════════════════════════════


def test_hr_table_count(hr_ddl: str):
    """#4: HR DDL parses 11 tables."""
    erd = parse_ddl(hr_ddl)
    assert len(erd.tables) == 11


def test_hr_fk_count(hr_ddl: str):
    """#5: HR DDL has 16 FK constraints."""
    erd = parse_ddl(hr_ddl)
    assert len(erd.foreign_keys) == 16


def test_hr_ontology(hr_ddl: str):
    """#6: HR ontology generates correct nodes."""
    erd = parse_ddl(hr_ddl)
    onto = build_ontology(erd)
    names = {nt.name for nt in onto.node_types}
    assert "Employee" in names
    assert "Department" in names
    assert "Project" in names
    assert "Skill" in names
    assert len(onto.node_types) >= 8


def test_hr_join_table_detection(hr_ddl: str):
    """#7: HR join tables (employee_skill, project_member) detected as relationships."""
    erd = parse_ddl(hr_ddl)
    onto = build_ontology(erd)
    # Join tables should generate relationship names, not nodes
    names = {nt.name for nt in onto.node_types}
    assert "EmployeeSkill" not in names
    assert "ProjectMember" not in names


# ════════════════════════════════════════════════════════════════════
#  Hospital Domain (11 tables, 12 FKs)
# ════════════════════════════════════════════════════════════════════


def test_hospital_table_count(hospital_ddl: str):
    """#8: Hospital DDL parses 11 tables."""
    erd = parse_ddl(hospital_ddl)
    assert len(erd.tables) == 11


def test_hospital_fk_count(hospital_ddl: str):
    """#9: Hospital DDL has 12 FK constraints."""
    erd = parse_ddl(hospital_ddl)
    assert len(erd.foreign_keys) == 12


def test_hospital_ontology(hospital_ddl: str):
    """#10: Hospital ontology generates correct nodes."""
    erd = parse_ddl(hospital_ddl)
    onto = build_ontology(erd)
    names = {nt.name for nt in onto.node_types}
    assert "Patient" in names
    assert "Doctor" in names
    assert "Appointment" in names
    assert "Medication" in names
    assert len(onto.node_types) == 11


def test_hospital_appointment_rels(hospital_ddl: str):
    """#11: Appointment connects Patient and Doctor."""
    erd = parse_ddl(hospital_ddl)
    onto = build_ontology(erd)
    # Check that Appointment has relationships pointing to Patient and Doctor
    rel_info = [(rt.source_node, rt.name, rt.target_node) for rt in onto.relationship_types]
    has_patient = any("Patient" in (s, t) and "Appointment" in (s, t) for s, _, t in rel_info)
    has_doctor = any("Doctor" in (s, t) and "Appointment" in (s, t) for s, _, t in rel_info)
    assert has_patient, f"No Patient-Appointment relationship found in {rel_info}"
    assert has_doctor, f"No Doctor-Appointment relationship found in {rel_info}"


# ════════════════════════════════════════════════════════════════════
#  Cross-Domain: Generic Pipeline
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ddl_fixture", ["accounting_ddl", "hr_ddl", "hospital_ddl"])
def test_cross_domain_pipeline(ddl_fixture: str, request):
    """#12: Full DDL→ontology pipeline works for all non-ecommerce domains."""
    ddl = request.getfixturevalue(ddl_fixture)
    erd = parse_ddl(ddl)
    onto = build_ontology(erd)

    # Basic sanity: nodes > 0, rels > 0, no empty labels
    assert len(onto.node_types) > 0
    assert len(onto.relationship_types) > 0
    for nt in onto.node_types:
        assert nt.name, f"Empty name in {ddl_fixture}"
        assert len(nt.properties) > 0, f"No properties on {nt.name}"
    for rt in onto.relationship_types:
        assert rt.name, f"Empty rel name in {ddl_fixture}"
        assert rt.source_node, f"Empty source in {ddl_fixture}"
        assert rt.target_node, f"Empty target in {ddl_fixture}"
