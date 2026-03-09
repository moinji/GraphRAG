"""Domain hints + quality checker tests."""

from __future__ import annotations

from app.models.schemas import (
    ColumnInfo,
    ERDSchema,
    ForeignKey,
    NodeType,
    OntologySpec,
    RelationshipType,
    TableInfo,
)
from app.ontology.domain_hints import (
    ECOMMERCE_HINT,
    EDUCATION_HINT,
    INSURANCE_HINT,
    detect_domain,
    get_domain_hint,
    list_domains,
)
from app.ontology.fk_rule_engine import build_ontology
from app.ontology.quality_checker import check_quality


# ════════════════════════════════════════════════════════════════════
#  Domain Detection Tests
# ════════════════════════════════════════════════════════════════════


def test_detect_ecommerce_domain(ecommerce_erd: ERDSchema):
    """Ecommerce ERD is correctly detected."""
    hint = detect_domain(ecommerce_erd)
    assert hint is not None
    assert hint.name == "ecommerce"


def test_detect_education_domain():
    """Education ERD is correctly detected."""
    erd = ERDSchema(
        tables=[
            TableInfo(name="students", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
            TableInfo(name="courses", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
            TableInfo(name="instructors", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
            TableInfo(name="departments", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
            TableInfo(name="enrollments", columns=[
                ColumnInfo(name="student_id", data_type="INTEGER"),
                ColumnInfo(name="course_id", data_type="INTEGER"),
            ], primary_key=None, primary_keys=["student_id", "course_id"]),
        ],
        foreign_keys=[
            ForeignKey(source_table="enrollments", source_column="student_id",
                       target_table="students", target_column="id"),
            ForeignKey(source_table="enrollments", source_column="course_id",
                       target_table="courses", target_column="id"),
        ],
    )
    hint = detect_domain(erd)
    assert hint is not None
    assert hint.name == "education"


def test_detect_insurance_domain():
    """Insurance ERD is correctly detected."""
    erd = ERDSchema(
        tables=[
            TableInfo(name="policyholders", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
            TableInfo(name="policies", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="policyholder_id", data_type="INTEGER"),
            ], primary_key="id"),
            TableInfo(name="claims", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="policy_id", data_type="INTEGER"),
            ], primary_key="id"),
            TableInfo(name="premiums", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="policy_id", data_type="INTEGER"),
            ], primary_key="id"),
            TableInfo(name="agents", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
        ],
        foreign_keys=[
            ForeignKey(source_table="policies", source_column="policyholder_id",
                       target_table="policyholders", target_column="id"),
            ForeignKey(source_table="claims", source_column="policy_id",
                       target_table="policies", target_column="id"),
            ForeignKey(source_table="premiums", source_column="policy_id",
                       target_table="policies", target_column="id"),
        ],
    )
    hint = detect_domain(erd)
    assert hint is not None
    assert hint.name == "insurance"


def test_detect_unknown_domain():
    """Unknown domain returns None."""
    erd = ERDSchema(
        tables=[
            TableInfo(name="galaxies", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
            ], primary_key="id"),
            TableInfo(name="stars", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="galaxy_id", data_type="INTEGER"),
            ], primary_key="id"),
        ],
        foreign_keys=[
            ForeignKey(source_table="stars", source_column="galaxy_id",
                       target_table="galaxies", target_column="id"),
        ],
    )
    hint = detect_domain(erd)
    assert hint is None


def test_get_domain_hint_by_name():
    """Get domain hint by explicit name."""
    assert get_domain_hint("ecommerce") is ECOMMERCE_HINT
    assert get_domain_hint("education") is EDUCATION_HINT
    assert get_domain_hint("insurance") is INSURANCE_HINT
    assert get_domain_hint("nonexistent") is None


def test_list_domains():
    """List all registered domains."""
    domains = list_domains()
    assert "ecommerce" in domains
    assert "education" in domains
    assert "insurance" in domains


# ════════════════════════════════════════════════════════════════════
#  FK Engine with Domain Hints
# ════════════════════════════════════════════════════════════════════


def test_ecommerce_with_hint_produces_same_result(ecommerce_erd: ERDSchema):
    """Ecommerce with explicit hint matches auto-detected result."""
    auto = build_ontology(ecommerce_erd)
    explicit = build_ontology(ecommerce_erd, domain_hint=ECOMMERCE_HINT)
    assert len(auto.node_types) == len(explicit.node_types)
    assert len(auto.relationship_types) == len(explicit.relationship_types)


def test_unknown_domain_auto_maps():
    """Unknown domain uses pure auto-mapping."""
    erd = ERDSchema(
        tables=[
            TableInfo(name="rockets", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="name", data_type="VARCHAR"),
            ], primary_key="id"),
            TableInfo(name="missions", columns=[
                ColumnInfo(name="id", data_type="SERIAL", is_primary_key=True),
                ColumnInfo(name="rocket_id", data_type="INTEGER"),
                ColumnInfo(name="destination", data_type="VARCHAR"),
            ], primary_key="id"),
        ],
        foreign_keys=[
            ForeignKey(source_table="missions", source_column="rocket_id",
                       target_table="rockets", target_column="id"),
        ],
    )
    ontology = build_ontology(erd)
    node_names = {n.name for n in ontology.node_types}
    assert "Rockets" in node_names
    assert "Missions" in node_names
    assert len(ontology.relationship_types) == 1
    assert ontology.relationship_types[0].name == "HAS_ROCKET"


def test_education_hint_join_table():
    """Education domain correctly maps enrollments as join table."""
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
            TableInfo(name="enrollments", columns=[
                ColumnInfo(name="student_id", data_type="INTEGER"),
                ColumnInfo(name="course_id", data_type="INTEGER"),
                ColumnInfo(name="grade", data_type="VARCHAR"),
                ColumnInfo(name="enrollment_date", data_type="DATE"),
                ColumnInfo(name="status", data_type="VARCHAR"),
            ], primary_key=None, primary_keys=["student_id", "course_id"]),
        ],
        foreign_keys=[
            ForeignKey(source_table="enrollments", source_column="student_id",
                       target_table="students", target_column="id"),
            ForeignKey(source_table="enrollments", source_column="course_id",
                       target_table="courses", target_column="id"),
        ],
    )
    ontology = build_ontology(erd, domain_hint=EDUCATION_HINT)
    # Students and Courses are nodes, enrollments is a join table
    node_names = {n.name for n in ontology.node_types}
    assert "Student" in node_names
    assert "Course" in node_names
    assert "Enrollments" not in node_names
    # ENROLLED_IN relationship with properties
    join_rels = [r for r in ontology.relationship_types if r.name == "ENROLLED_IN"]
    assert len(join_rels) == 1
    prop_names = {p.name for p in join_rels[0].properties}
    assert "grade" in prop_names
    assert "enrollment_date" in prop_names


# ════════════════════════════════════════════════════════════════════
#  Quality Checker Tests
# ════════════════════════════════════════════════════════════════════


def test_quality_clean_ontology(ecommerce_erd: ERDSchema):
    """Clean ecommerce ontology passes quality checks."""
    ontology = build_ontology(ecommerce_erd)
    report = check_quality(ontology)
    assert report.passed
    assert report.score == 1.0
    assert report.error_count == 0


def test_quality_duplicate_class():
    """Duplicate node names are flagged as errors."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="Product", source_table="products", properties=[]),
            NodeType(name="product", source_table="items", properties=[]),  # case-insensitive dup
        ],
        relationship_types=[],
    )
    report = check_quality(ontology)
    assert not report.passed
    dup_issues = [i for i in report.issues if i.category == "duplicate_class"]
    assert len(dup_issues) == 1


def test_quality_domain_range_error():
    """Relationship referencing non-existent node is flagged."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="Product", source_table="products", properties=[]),
        ],
        relationship_types=[
            RelationshipType(
                name="BOUGHT_BY",
                source_node="Product",
                target_node="NonExistent",
                data_table="orders",
                source_key_column="id",
                target_key_column="product_id",
            ),
        ],
    )
    report = check_quality(ontology)
    assert not report.passed
    dr_issues = [i for i in report.issues if i.category == "domain_range"]
    assert len(dr_issues) == 1
    assert "NonExistent" in dr_issues[0].message


def test_quality_orphan_node():
    """Node with no relationships is flagged as warning."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="Product", source_table="products", properties=[]),
            NodeType(name="Orphan", source_table="orphans", properties=[]),
        ],
        relationship_types=[
            RelationshipType(
                name="SELF_REF",
                source_node="Product",
                target_node="Product",
                data_table="products",
                source_key_column="id",
                target_key_column="parent_id",
            ),
        ],
    )
    report = check_quality(ontology)
    # Orphan is a warning, not an error
    assert report.passed
    orphan_issues = [i for i in report.issues if i.category == "orphan"]
    assert len(orphan_issues) == 1
    assert "Orphan" in orphan_issues[0].message


def test_quality_naming_convention():
    """Bad naming conventions are flagged as warnings."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="product", source_table="products", properties=[]),  # lowercase
        ],
        relationship_types=[
            RelationshipType(
                name="BoughtBy",  # not UPPER_SNAKE
                source_node="product",
                target_node="product",
                data_table="orders",
                source_key_column="id",
                target_key_column="product_id",
            ),
        ],
    )
    report = check_quality(ontology)
    naming_issues = [i for i in report.issues if i.category == "naming"]
    assert len(naming_issues) >= 2  # node + relationship naming issues


def test_quality_circular_ref():
    """Multi-node circular reference is flagged as warning."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="A", source_table="a", properties=[]),
            NodeType(name="B", source_table="b", properties=[]),
            NodeType(name="C", source_table="c", properties=[]),
        ],
        relationship_types=[
            RelationshipType(name="A_TO_B", source_node="A", target_node="B",
                             data_table="ab", source_key_column="id", target_key_column="a_id"),
            RelationshipType(name="B_TO_C", source_node="B", target_node="C",
                             data_table="bc", source_key_column="id", target_key_column="b_id"),
            RelationshipType(name="C_TO_A", source_node="C", target_node="A",
                             data_table="ca", source_key_column="id", target_key_column="c_id"),
        ],
    )
    report = check_quality(ontology)
    cycle_issues = [i for i in report.issues if i.category == "circular_ref"]
    assert len(cycle_issues) >= 1


def test_quality_self_ref_not_flagged():
    """Self-referential relationships (like PARENT_OF) are NOT flagged as circular."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="Category", source_table="categories", properties=[]),
        ],
        relationship_types=[
            RelationshipType(
                name="PARENT_OF",
                source_node="Category",
                target_node="Category",
                data_table="categories",
                source_key_column="parent_id",
                target_key_column="id",
            ),
        ],
    )
    report = check_quality(ontology)
    cycle_issues = [i for i in report.issues if i.category == "circular_ref"]
    assert len(cycle_issues) == 0
