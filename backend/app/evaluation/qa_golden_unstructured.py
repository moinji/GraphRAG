"""QA golden pairs for unstructured data (Mode C hybrid search).

These test cases assume documents have been uploaded describing the same
e-commerce domain as the structured data. Mode C should be able to answer
by combining vector-searched document chunks with KG context.

Categories:
  - doc_only (5): answer only exists in documents, not in KG
  - hybrid (5): answer needs both document + KG data
  - doc_entity (5): question about entities found via NER in documents
"""

from __future__ import annotations

from app.models.schemas import QAGoldenPair

QA_GOLDEN_PAIRS_UNSTRUCTURED: list[QAGoldenPair] = [
    # ── doc_only — 5개 (답변이 문서에만 존재) ──────────────────
    QAGoldenPair(
        id="U-D01",
        question="맥북프로의 배터리 수명은 얼마나 되나요?",
        category="doc_only",
        difficulty="easy",
        expected_keywords=["시간", "배터리"],
        expected_entities=["맥북프로"],
    ),
    QAGoldenPair(
        id="U-D02",
        question="에어팟프로의 노이즈캔슬링 기능에 대해 설명해주세요.",
        category="doc_only",
        difficulty="medium",
        expected_keywords=["노이즈캔슬링", "ANC"],
        expected_entities=["에어팟프로"],
    ),
    QAGoldenPair(
        id="U-D03",
        question="반품 정책은 어떻게 되나요?",
        category="doc_only",
        difficulty="easy",
        expected_keywords=["반품", "일"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-D04",
        question="배송 소요 시간은 얼마나 걸리나요?",
        category="doc_only",
        difficulty="easy",
        expected_keywords=["배송", "일"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-D05",
        question="LG그램의 무게는 얼마인가요?",
        category="doc_only",
        difficulty="easy",
        expected_keywords=["kg", "그램"],
        expected_entities=["LG그램"],
    ),

    # ── hybrid — 5개 (문서 + KG 결합 필요) ──────────────────
    QAGoldenPair(
        id="U-H01",
        question="김민수가 주문한 맥북프로의 주요 사양은?",
        category="hybrid",
        difficulty="medium",
        expected_keywords=["맥북프로"],
        expected_entities=["김민수", "맥북프로"],
    ),
    QAGoldenPair(
        id="U-H02",
        question="애플코리아가 공급하는 제품들의 특징을 문서에서 찾아주세요.",
        category="hybrid",
        difficulty="hard",
        expected_keywords=["애플"],
        expected_entities=["애플코리아"],
    ),
    QAGoldenPair(
        id="U-H03",
        question="노트북 카테고리에 속한 제품들의 리뷰 내용은?",
        category="hybrid",
        difficulty="hard",
        expected_keywords=["노트북"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-H04",
        question="이영희가 구매한 갤럭시버즈의 장단점은?",
        category="hybrid",
        difficulty="medium",
        expected_keywords=["갤럭시버즈"],
        expected_entities=["이영희", "갤럭시버즈"],
    ),
    QAGoldenPair(
        id="U-H05",
        question="오디오 카테고리 제품 중 문서에 언급된 사양을 비교해주세요.",
        category="hybrid",
        difficulty="hard",
        expected_keywords=["오디오"],
        expected_entities=[],
    ),

    # ── doc_entity — 5개 (문서 NER로 발견된 엔티티) ──────────────
    QAGoldenPair(
        id="U-E01",
        question="문서에서 언급된 주요 브랜드는 무엇인가요?",
        category="doc_entity",
        difficulty="easy",
        expected_keywords=["애플", "삼성"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-E02",
        question="제품 설명서에서 언급된 고객 이름이 있나요?",
        category="doc_entity",
        difficulty="medium",
        expected_keywords=[],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-E03",
        question="문서에서 가장 많이 언급된 제품은?",
        category="doc_entity",
        difficulty="medium",
        expected_keywords=[],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-E04",
        question="제품 매뉴얼에서 소니WH-1000XM5에 대한 정보가 있나요?",
        category="doc_entity",
        difficulty="easy",
        expected_keywords=["소니", "WH-1000XM5"],
        expected_entities=["소니WH-1000XM5"],
    ),
    QAGoldenPair(
        id="U-E05",
        question="갤럭시탭 관련 문서 내용을 요약해주세요.",
        category="doc_entity",
        difficulty="medium",
        expected_keywords=["갤럭시탭"],
        expected_entities=["갤럭시탭"],
    ),
]
