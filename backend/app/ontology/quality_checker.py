"""Ontology quality checker based on Protégé validation criteria.

Checks:
1. Circular references (cycles in relationship graph)
2. Duplicate class names
3. Domain/Range errors (source/target node references non-existent nodes)
4. Orphan nodes (nodes with no relationships)
5. Naming convention violations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.models.schemas import OntologySpec

logger = logging.getLogger(__name__)


@dataclass
class QualityIssue:
    """A single quality issue found in the ontology."""

    severity: str  # "error" | "warning"
    category: str  # "circular_ref" | "duplicate_class" | "domain_range" | "orphan" | "naming"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class QualityReport:
    """Aggregated quality check results."""

    issues: list[QualityIssue] = field(default_factory=list)
    score: float = 1.0  # 0.0 (worst) ~ 1.0 (perfect)
    checked: bool = True

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def passed(self) -> bool:
        return self.error_count == 0


def check_quality(ontology: OntologySpec) -> QualityReport:
    """Run all quality checks on an OntologySpec.

    Returns a QualityReport with issues and an overall score.
    """
    issues: list[QualityIssue] = []

    issues.extend(_check_duplicate_classes(ontology))
    issues.extend(_check_domain_range(ontology))
    issues.extend(_check_circular_refs(ontology))
    issues.extend(_check_orphan_nodes(ontology))
    issues.extend(_check_naming_conventions(ontology))

    # Score: 1.0 - (0.2 per error, 0.05 per warning), floor at 0.0
    penalty = sum(0.2 for i in issues if i.severity == "error") + sum(
        0.05 for i in issues if i.severity == "warning"
    )
    score = max(0.0, 1.0 - penalty)

    report = QualityReport(issues=issues, score=round(score, 2))

    if issues:
        logger.info(
            "Quality check: %d errors, %d warnings, score=%.2f",
            report.error_count,
            report.warning_count,
            report.score,
        )
    else:
        logger.info("Quality check passed: no issues found")

    return report


def _check_duplicate_classes(ontology: OntologySpec) -> list[QualityIssue]:
    """Check for duplicate node type names (case-insensitive)."""
    issues: list[QualityIssue] = []
    seen: dict[str, str] = {}  # lowercase → original

    for nt in ontology.node_types:
        lower = nt.name.lower()
        if lower in seen:
            issues.append(
                QualityIssue(
                    severity="error",
                    category="duplicate_class",
                    message=f"Duplicate node type: '{nt.name}' conflicts with '{seen[lower]}'",
                    details={"node_a": seen[lower], "node_b": nt.name},
                )
            )
        else:
            seen[lower] = nt.name

    return issues


def _check_domain_range(ontology: OntologySpec) -> list[QualityIssue]:
    """Check that all relationship source/target nodes exist."""
    issues: list[QualityIssue] = []
    node_names = {nt.name for nt in ontology.node_types}

    for rt in ontology.relationship_types:
        if rt.source_node not in node_names:
            issues.append(
                QualityIssue(
                    severity="error",
                    category="domain_range",
                    message=f"Relationship '{rt.name}' source_node '{rt.source_node}' does not exist",
                    details={"relationship": rt.name, "missing_node": rt.source_node, "role": "source"},
                )
            )
        if rt.target_node not in node_names:
            issues.append(
                QualityIssue(
                    severity="error",
                    category="domain_range",
                    message=f"Relationship '{rt.name}' target_node '{rt.target_node}' does not exist",
                    details={"relationship": rt.name, "missing_node": rt.target_node, "role": "target"},
                )
            )

    return issues


def _check_circular_refs(ontology: OntologySpec) -> list[QualityIssue]:
    """Detect cycles in the relationship graph (excluding self-referential).

    Self-referential relationships (e.g., Category PARENT_OF Category) are
    valid and expected — only multi-node cycles are flagged.
    """
    issues: list[QualityIssue] = []

    # Build adjacency list (exclude self-loops)
    graph: dict[str, set[str]] = {}
    for rt in ontology.relationship_types:
        if rt.source_node == rt.target_node:
            continue
        graph.setdefault(rt.source_node, set()).add(rt.target_node)

    # DFS cycle detection
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles_found: list[list[str]] = []

    def _dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        in_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                _dfs(neighbor, path)
            elif neighbor in in_stack:
                # Found a cycle — extract it
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles_found.append(cycle)

        path.pop()
        in_stack.discard(node)

    for node in graph:
        if node not in visited:
            _dfs(node, [])

    for cycle in cycles_found:
        cycle_str = " → ".join(cycle)
        issues.append(
            QualityIssue(
                severity="warning",
                category="circular_ref",
                message=f"Circular reference detected: {cycle_str}",
                details={"cycle": cycle},
            )
        )

    return issues


def _check_orphan_nodes(ontology: OntologySpec) -> list[QualityIssue]:
    """Detect nodes that have no relationships."""
    issues: list[QualityIssue] = []
    connected: set[str] = set()

    for rt in ontology.relationship_types:
        connected.add(rt.source_node)
        connected.add(rt.target_node)

    for nt in ontology.node_types:
        if nt.name not in connected:
            issues.append(
                QualityIssue(
                    severity="warning",
                    category="orphan",
                    message=f"Orphan node '{nt.name}' has no relationships",
                    details={"node": nt.name},
                )
            )

    return issues


def _is_valid_node_name(name: str) -> bool:
    """Check if name is valid: PascalCase ASCII or any non-ASCII script (Korean, CJK)."""
    if not name:
        return False
    first_char = name[0]
    return first_char.isupper() or not first_char.isascii()


def _check_naming_conventions(ontology: OntologySpec) -> list[QualityIssue]:
    """Check naming conventions: PascalCase nodes, UPPER_SNAKE relationships."""
    issues: list[QualityIssue] = []

    for nt in ontology.node_types:
        if not _is_valid_node_name(nt.name):
            issues.append(
                QualityIssue(
                    severity="warning",
                    category="naming",
                    message=f"Node type '{nt.name}' should be PascalCase",
                    details={"node": nt.name},
                )
            )

    for rt in ontology.relationship_types:
        if rt.name != rt.name.upper():
            issues.append(
                QualityIssue(
                    severity="warning",
                    category="naming",
                    message=f"Relationship '{rt.name}' should be UPPER_SNAKE_CASE",
                    details={"relationship": rt.name},
                )
            )

    return issues
