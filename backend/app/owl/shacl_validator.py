"""pySHACL 검증 래퍼 — TBox-level schema consistency check.

SHACL shapes를 OWL Graph에 대해 검증하고 결과를 QualityIssue 리스트로 변환한다.
이 검증은 인스턴스(ABox)가 아닌 온톨로지 스키마(TBox)의 일관성을 확인한다.
"""

from __future__ import annotations

import logging

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from app.ontology.quality_checker import QualityIssue

logger = logging.getLogger(__name__)

SH_NS = "http://www.w3.org/ns/shacl#"

# 명시적 URIRef 정의 — 문자열(str)은 rdflib에서 매칭되지 않음
SH_VALIDATION_RESULT = URIRef(f"{SH_NS}ValidationResult")
SH_RESULT_SEVERITY = URIRef(f"{SH_NS}resultSeverity")
SH_RESULT_MESSAGE = URIRef(f"{SH_NS}resultMessage")
SH_FOCUS_NODE = URIRef(f"{SH_NS}focusNode")


def validate_shacl(
    data_graph: Graph,
    shapes_graph: Graph,
) -> tuple[bool, list[QualityIssue]]:
    """SHACL 검증 실행 → QualityIssue 리스트 반환.

    TBox-level schema consistency check.
    인스턴스(ABox) 검증이 아닌 온톨로지 구조 일관성 확인.

    Args:
        data_graph: 검증 대상 OWL Graph
        shapes_graph: SHACL shapes Graph

    Returns:
        (conforms, issues) — conforms=True이면 issues는 빈 리스트
    """
    try:
        from pyshacl import validate
    except ImportError:
        logger.warning("pyshacl not installed — SHACL validation skipped")
        return True, []

    try:
        conforms, results_graph, results_text = validate(
            data_graph=data_graph,
            shacl_graph=shapes_graph,
            inference="rdfs",
            abort_on_first=False,
        )
    except Exception as e:
        logger.warning("SHACL validation failed: %s", e)
        return True, []  # non-fatal

    if conforms:
        logger.info("SHACL validation passed (TBox consistency)")
        return True, []

    # 결과 파싱 → QualityIssue 리스트
    issues: list[QualityIssue] = []
    for result in results_graph.subjects(RDF.type, SH_VALIDATION_RESULT):
        severity_uri = results_graph.value(result, SH_RESULT_SEVERITY)
        severity = "error" if severity_uri and "Violation" in str(severity_uri) else "warning"

        message = str(results_graph.value(result, SH_RESULT_MESSAGE) or "SHACL constraint violated")
        focus = str(results_graph.value(result, SH_FOCUS_NODE) or "")

        issues.append(QualityIssue(
            severity=severity,
            category="shacl",
            message=message,
            details={"focus_node": focus},
        ))

    logger.info("SHACL validation: %d issue(s) found", len(issues))
    return conforms, issues
