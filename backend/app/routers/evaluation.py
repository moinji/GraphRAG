"""Evaluation API: POST /run, GET /golden, POST /run-c."""

from __future__ import annotations

from fastapi import APIRouter

from app.evaluation.qa_evaluator import (
    build_comparison,
    run_evaluation_a,
    run_evaluation_b,
    run_evaluation_c,
)
from app.evaluation.qa_golden import QA_GOLDEN_PAIRS
from app.evaluation.qa_golden_unstructured import QA_GOLDEN_PAIRS_UNSTRUCTURED
from app.models.schemas import QAComparisonReport, QAGoldenPair, QASingleResult

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.get("/golden", response_model=list[QAGoldenPair])
def get_golden_pairs() -> list[QAGoldenPair]:
    """Return all 50 QA golden pairs (structured)."""
    return QA_GOLDEN_PAIRS


@router.get("/golden/unstructured", response_model=list[QAGoldenPair])
def get_golden_pairs_unstructured() -> list[QAGoldenPair]:
    """Return 15 QA golden pairs for unstructured data."""
    return QA_GOLDEN_PAIRS_UNSTRUCTURED


@router.post("/run", response_model=QAComparisonReport)
def run_evaluation() -> QAComparisonReport:
    """Run full A/B evaluation against golden pairs."""
    a_results = run_evaluation_a(QA_GOLDEN_PAIRS)
    b_results = run_evaluation_b(QA_GOLDEN_PAIRS)
    return build_comparison(a_results, b_results)


@router.post("/run-c", response_model=list[QASingleResult])
def run_evaluation_mode_c() -> list[QASingleResult]:
    """Run Mode C evaluation against unstructured golden pairs."""
    return run_evaluation_c(QA_GOLDEN_PAIRS_UNSTRUCTURED)
