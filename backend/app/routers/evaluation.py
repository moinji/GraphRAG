"""Evaluation API: POST /run, GET /golden."""

from __future__ import annotations

from fastapi import APIRouter

from app.evaluation.qa_evaluator import (
    build_comparison,
    run_evaluation_a,
    run_evaluation_b,
)
from app.evaluation.qa_golden import QA_GOLDEN_PAIRS
from app.models.schemas import QAComparisonReport, QAGoldenPair

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.get("/golden", response_model=list[QAGoldenPair])
def get_golden_pairs() -> list[QAGoldenPair]:
    """Return all 50 QA golden pairs."""
    return QA_GOLDEN_PAIRS


@router.post("/run", response_model=QAComparisonReport)
def run_evaluation() -> QAComparisonReport:
    """Run full A/B evaluation against golden pairs."""
    a_results = run_evaluation_a(QA_GOLDEN_PAIRS)
    b_results = run_evaluation_b(QA_GOLDEN_PAIRS)
    return build_comparison(a_results, b_results)
