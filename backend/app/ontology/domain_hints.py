"""Pluggable domain hint system for ontology generation.

Domain hints provide optional overrides for known table→label mappings,
join-table configs, FK direction overrides, and LLM prompt hints.
The FK rule engine uses auto-mapping by default; hints improve quality
for known domains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.models.schemas import ERDSchema

logger = logging.getLogger(__name__)


@dataclass
class DomainHint:
    """Configuration hints for a specific domain."""

    name: str  # e.g. "ecommerce", "education", "insurance"

    # table_name → PascalCase node label
    table_to_label: dict[str, str] = field(default_factory=dict)

    # join tables that become relationships instead of nodes
    join_table_config: dict[str, dict] = field(default_factory=dict)

    # (source_table, source_column) → (src_label, rel_name, tgt_label, src_key, tgt_key)
    direction_map: dict[tuple[str, str], tuple[str, str, str, str, str]] = field(
        default_factory=dict
    )

    # LLM enrichment prompt hint text
    llm_prompt_hint: str = ""

    # Signature table names used for domain detection
    signature_tables: set[str] = field(default_factory=set)

    # Minimum overlap count to detect this domain
    detection_threshold: int = 6


# ── E-commerce domain ────────────────────────────────────────────

ECOMMERCE_HINT = DomainHint(
    name="ecommerce",
    table_to_label={
        "addresses": "Address",
        "categories": "Category",
        "suppliers": "Supplier",
        "coupons": "Coupon",
        "customers": "Customer",
        "products": "Product",
        "orders": "Order",
        "payments": "Payment",
        "reviews": "Review",
    },
    join_table_config={
        "order_items": {
            "rel_name": "CONTAINS",
            "source_fk_col": "order_id",
            "target_fk_col": "product_id",
            "property_columns": ["quantity", "unit_price"],
        },
        "wishlists": {
            "rel_name": "WISHLISTED",
            "source_fk_col": "customer_id",
            "target_fk_col": "product_id",
            "property_columns": [],
        },
        "shipping": {
            "rel_name": "SHIPPED_TO",
            "source_fk_col": "order_id",
            "target_fk_col": "address_id",
            "property_columns": ["carrier", "tracking_number", "status"],
        },
    },
    direction_map={
        ("customers", "address_id"): ("Customer", "LIVES_AT", "Address", "id", "address_id"),
        ("products", "category_id"): ("Product", "BELONGS_TO", "Category", "id", "category_id"),
        ("products", "supplier_id"): ("Product", "SUPPLIED_BY", "Supplier", "id", "supplier_id"),
        ("orders", "coupon_id"): ("Order", "USED_COUPON", "Coupon", "id", "coupon_id"),
        ("reviews", "product_id"): ("Review", "REVIEWS", "Product", "id", "product_id"),
        ("orders", "customer_id"): ("Customer", "PLACED", "Order", "customer_id", "id"),
        ("payments", "order_id"): ("Order", "PAID_BY", "Payment", "order_id", "id"),
        ("reviews", "customer_id"): ("Customer", "WROTE", "Review", "customer_id", "id"),
        ("categories", "parent_id"): ("Category", "PARENT_OF", "Category", "parent_id", "id"),
    },
    llm_prompt_hint="""\
Domain: E-commerce.
Common patterns to consider:
- Customers who buy similar products (collaborative filtering edges)
- Product bundles / frequently-bought-together
- Category hierarchy traversal
- Supplier → Product → Review sentiment aggregation
- Order lifecycle status edges (PENDING → SHIPPED → DELIVERED)

Only add relationships that are genuinely useful for graph queries. \
Do not add speculative edges without clear query value.
""",
    signature_tables={
        "customers", "products", "orders", "payments", "reviews",
        "categories", "suppliers", "coupons", "addresses",
        "order_items", "wishlists", "shipping",
    },
    detection_threshold=6,
)


# ── Education domain ─────────────────────────────────────────────

EDUCATION_HINT = DomainHint(
    name="education",
    table_to_label={
        "students": "Student",
        "courses": "Course",
        "instructors": "Instructor",
        "departments": "Department",
        "enrollments": "Enrollment",
        "assignments": "Assignment",
        "grades": "Grade",
        "semesters": "Semester",
        "classrooms": "Classroom",
        "prerequisites": "Prerequisite",
        "certificates": "Certificate",
        "competencies": "Competency",
    },
    join_table_config={
        "enrollments": {
            "rel_name": "ENROLLED_IN",
            "source_fk_col": "student_id",
            "target_fk_col": "course_id",
            "property_columns": ["grade", "enrollment_date", "status"],
        },
        "prerequisites": {
            "rel_name": "REQUIRES",
            "source_fk_col": "course_id",
            "target_fk_col": "prerequisite_id",
            "property_columns": [],
        },
    },
    direction_map={
        ("courses", "department_id"): ("Course", "OFFERED_BY", "Department", "id", "department_id"),
        ("courses", "instructor_id"): ("Instructor", "TEACHES", "Course", "instructor_id", "id"),
        ("instructors", "department_id"): ("Instructor", "BELONGS_TO", "Department", "id", "department_id"),
        ("assignments", "course_id"): ("Course", "HAS_ASSIGNMENT", "Assignment", "course_id", "id"),
        ("grades", "student_id"): ("Student", "RECEIVED", "Grade", "student_id", "id"),
        ("grades", "assignment_id"): ("Grade", "FOR_ASSIGNMENT", "Assignment", "id", "assignment_id"),
        ("certificates", "student_id"): ("Student", "EARNED", "Certificate", "student_id", "id"),
        ("certificates", "course_id"): ("Certificate", "CERTIFIES", "Course", "id", "course_id"),
    },
    llm_prompt_hint="""\
Domain: Education / Learning Management.
Common patterns to consider:
- Learning path dependencies (prerequisite chains)
- Student performance across courses (grade progression)
- Instructor influence on student outcomes
- Competency mapping (course → skills acquired)
- Semester-based enrollment patterns
- Certificate/credential pathways

Focus on relationships that enable multi-hop queries like:
"What prerequisites does a student need for course X?"
"Which instructors have the highest completion rates?"
""",
    signature_tables={
        "students", "courses", "instructors", "departments",
        "enrollments", "assignments", "grades", "semesters",
        "classrooms", "prerequisites", "certificates",
    },
    detection_threshold=4,
)


# ── Insurance domain ─────────────────────────────────────────────

INSURANCE_HINT = DomainHint(
    name="insurance",
    table_to_label={
        "policyholders": "Policyholder",
        "policies": "Policy",
        "products": "Product",
        "claims": "Claim",
        "claim_items": "ClaimItem",
        "coverage": "Coverage",
        "coverages": "Coverage",
        "premiums": "Premium",
        "agents": "Agent",
        "beneficiaries": "Beneficiary",
        "exclusions": "Exclusion",
        "riders": "Rider",
        "underwriting": "Underwriting",
        "renewals": "Renewal",
        "settlements": "Settlement",
        "clauses": "Clause",
    },
    join_table_config={
        "policy_coverages": {
            "rel_name": "COVERS",
            "source_fk_col": "policy_id",
            "target_fk_col": "coverage_id",
            "property_columns": ["limit_amount", "deductible"],
        },
        "policy_exclusions": {
            "rel_name": "EXCLUDES",
            "source_fk_col": "policy_id",
            "target_fk_col": "exclusion_id",
            "property_columns": [],
        },
    },
    direction_map={
        ("policies", "policyholder_id"): ("Policyholder", "HOLDS", "Policy", "policyholder_id", "id"),
        ("policies", "product_id"): ("Policy", "IS_TYPE", "Product", "id", "product_id"),
        ("policies", "agent_id"): ("Agent", "SOLD", "Policy", "agent_id", "id"),
        ("claims", "policy_id"): ("Policy", "HAS_CLAIM", "Claim", "policy_id", "id"),
        ("claims", "policyholder_id"): ("Policyholder", "FILED", "Claim", "policyholder_id", "id"),
        ("claim_items", "claim_id"): ("Claim", "INCLUDES", "ClaimItem", "claim_id", "id"),
        ("premiums", "policy_id"): ("Policy", "CHARGED", "Premium", "policy_id", "id"),
        ("beneficiaries", "policy_id"): ("Policy", "BENEFITS", "Beneficiary", "policy_id", "id"),
        ("riders", "policy_id"): ("Policy", "HAS_RIDER", "Rider", "policy_id", "id"),
        ("settlements", "claim_id"): ("Claim", "SETTLED_BY", "Settlement", "claim_id", "id"),
        ("renewals", "policy_id"): ("Policy", "RENEWED_AS", "Renewal", "policy_id", "id"),
    },
    llm_prompt_hint="""\
Domain: Insurance.
Common patterns to consider:
- Policy → Coverage → Exclusion chain (what's covered vs excluded)
- Claim → Settlement → Payout flow
- Policyholder → Policy → Beneficiary relationship
- Underwriting risk assessment paths
- Renewal history and premium trends
- Clause/Article → Exception → Precedent references

Focus on relationships that enable multi-hop queries like:
"What exclusions apply to this claim?"
"Contract(C-001) → Exclusion(E-003) → Procedure(P-089) → Pre-approval status"
"What is the claim rejection probability based on policy terms?"
""",
    signature_tables={
        "policyholders", "policies", "claims", "coverage", "coverages",
        "premiums", "agents", "beneficiaries", "exclusions",
        "riders", "underwriting", "renewals", "settlements",
        "claim_items", "clauses",
    },
    detection_threshold=4,
)


# ── Domain registry ──────────────────────────────────────────────

_DOMAIN_REGISTRY: list[DomainHint] = [
    ECOMMERCE_HINT,
    EDUCATION_HINT,
    INSURANCE_HINT,
]


def detect_domain(erd: ERDSchema) -> DomainHint | None:
    """Auto-detect domain from ERD table names.

    Returns the best-matching DomainHint, or None if no domain matches.
    """
    table_names = {t.name.lower() for t in erd.tables}

    best: DomainHint | None = None
    best_overlap = 0

    for hint in _DOMAIN_REGISTRY:
        overlap = len(table_names & hint.signature_tables)
        if overlap >= hint.detection_threshold and overlap > best_overlap:
            best = hint
            best_overlap = overlap

    if best:
        logger.info("Auto-detected domain: %s (overlap=%d)", best.name, best_overlap)
    else:
        logger.info("No domain detected — using pure auto-mapping")

    return best


def get_domain_hint(domain_name: str) -> DomainHint | None:
    """Get a domain hint by name."""
    for hint in _DOMAIN_REGISTRY:
        if hint.name == domain_name:
            return hint
    return None


def list_domains() -> list[str]:
    """List all registered domain names."""
    return [h.name for h in _DOMAIN_REGISTRY]
