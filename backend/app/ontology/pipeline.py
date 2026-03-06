"""Two-stage ontology generation pipeline.

Stage 1: FK rule engine (deterministic)
Stage 2: Claude LLM enrichment (optional, non-fatal)
"""

from __future__ import annotations

import logging

from app.db.pg_client import compute_erd_hash, save_version
from app.evaluation.auto_golden import generate_golden_from_ontology, is_ecommerce_domain
from app.evaluation.evaluator import evaluate
from app.evaluation.golden_ecommerce import (
    GOLDEN_NODE_NAMES,
    GOLDEN_RELATIONSHIP_SPECS,
)
from app.exceptions import LLMEnrichmentError, OntologyGenerationError
from app.models.schemas import (
    ERDSchema,
    EvalMetrics,
    LLMEnrichmentDiff,
    OntologyGenerateResponse,
    OntologySpec,
)
from app.ontology.fk_rule_engine import build_ontology

logger = logging.getLogger(__name__)


def generate_ontology(
    erd: ERDSchema,
    skip_llm: bool = False,
    tenant_id: str | None = None,
) -> OntologyGenerateResponse:
    """Run the full ontology generation pipeline.

    1. Stage 1: FK rule engine → baseline ontology
    2. Stage 2 (optional): Claude LLM enrichment
    3. Evaluation against golden data
    4. PG version storage (best-effort)
    """
    # ── Stage 1: FK rule engine ────────────────────────────────────
    try:
        baseline = build_ontology(erd)
    except Exception as e:
        raise OntologyGenerationError(f"FK rule engine failed: {e}")

    final_ontology = baseline
    stage = "fk_only"
    llm_diffs: list[LLMEnrichmentDiff] = []

    # ── Stage 2: LLM enrichment (optional) ─────────────────────────
    if not skip_llm:
        try:
            from app.ontology.llm_enricher import enrich_ontology

            erd_dict = erd.model_dump()
            enriched, diffs = enrich_ontology(baseline, erd_dict)
            final_ontology = enriched
            llm_diffs = diffs
            stage = "fk_plus_llm"
        except LLMEnrichmentError as e:
            logger.warning("LLM enrichment skipped: %s", e.detail)
            # Keep baseline, stage stays "fk_only"

    # ── Evaluation ─────────────────────────────────────────────────
    warnings: list[str] = []
    eval_report: EvalMetrics | None = None
    try:
        # Use ecommerce golden for ecommerce domains, auto-golden otherwise
        if is_ecommerce_domain(final_ontology):
            golden_nodes = GOLDEN_NODE_NAMES
            golden_rels = GOLDEN_RELATIONSHIP_SPECS
        else:
            golden_nodes, golden_rels = generate_golden_from_ontology(final_ontology)
            warnings.append("자동 생성된 golden 데이터로 평가됩니다 (도메인별 golden 미등록).")
        eval_report = evaluate(
            final_ontology,
            golden_nodes,
            golden_rels,
        )
    except Exception:
        logger.error("Evaluation failed — results will be missing", exc_info=True)
        warnings.append("평가 실행 실패: eval_report가 없습니다.")

    # ── PG storage (best-effort) ───────────────────────────────────
    version_id: int | None = None
    try:
        erd_hash = compute_erd_hash(erd.model_dump())
        version_id = save_version(
            erd_hash=erd_hash,
            ontology_json=final_ontology.model_dump(),
            eval_json=eval_report.model_dump() if eval_report else None,
            tenant_id=tenant_id,
        )
    except Exception:
        logger.error("PG version save failed — version_id will be None", exc_info=True)
        warnings.append("PostgreSQL 저장 실패: 버전이 저장되지 않았습니다.")

    return OntologyGenerateResponse(
        ontology=final_ontology,
        eval_report=eval_report,
        llm_diffs=llm_diffs,
        version_id=version_id,
        stage=stage,
        warnings=warnings,
    )
