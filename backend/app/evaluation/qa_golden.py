"""50 QA golden pairs for comprehensive evaluation.

Seed data mapping (from generator.py):
  Customers: 김민수(1), 이영희(2), 박지훈(3), 최수진(4), 정대현(5)
  Products: 맥북프로(1,cat4,sup1), 에어팟프로(2,cat5,sup1), 갤럭시탭(3,cat6,sup2),
            LG그램(4,cat4,sup3), 갤럭시버즈(5,cat5,sup2), 아이패드에어(6,cat6,sup1),
            맥북에어(7,cat4,sup1), 소니WH-1000XM5(8,cat5,sup3)
  Categories: 전자기기(1), 의류(2), 식품(3), 노트북(4), 오디오(5), 태블릿(6)
  Suppliers: 애플코리아(1), 삼성전자(2), LG전자(3)

  김민수: orders 1,2,8 → 맥북프로, 에어팟프로, 갤럭시탭
  이영희: orders 3,5 → LG그램, 갤럭시버즈, 맥북프로, 소니WH-1000XM5
  박지훈: order 4  → 아이패드에어, 맥북프로
  최수진: order 6  → 맥북에어
  정대현: order 7  → 에어팟프로, LG그램
"""

from __future__ import annotations

from app.models.schemas import QAGoldenPair

QA_GOLDEN_PAIRS: list[QAGoldenPair] = [
    # ── traverse (1홉) — 10개 ────────────────────────────────────
    QAGoldenPair(
        id="T1-01", question="김민수의 이메일 주소는?",
        category="traverse", difficulty="easy",
        expected_keywords=["minsu@example.com"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="T1-02", question="이영희의 전화번호는?",
        category="traverse", difficulty="easy",
        expected_keywords=["010-2345-6789"],
        expected_entities=["이영희"],
    ),
    QAGoldenPair(
        id="T1-03", question="맥북프로의 가격은?",
        category="traverse", difficulty="easy",
        expected_keywords=["3500000"],
        expected_entities=["맥북프로"],
    ),
    QAGoldenPair(
        id="T1-04", question="맥북프로의 공급업체는?",
        category="traverse", difficulty="easy",
        expected_keywords=["애플코리아"],
        expected_entities=["맥북프로"],
    ),
    QAGoldenPair(
        id="T1-05", question="김민수의 주소는 어디인가요?",
        category="traverse", difficulty="easy",
        expected_keywords=["강남구", "테헤란로"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="T1-06", question="에어팟프로의 카테고리는?",
        category="traverse", difficulty="easy",
        expected_keywords=["오디오"],
        expected_entities=["에어팟프로"],
    ),
    QAGoldenPair(
        id="T1-07", question="박지훈의 이메일은?",
        category="traverse", difficulty="easy",
        expected_keywords=["jihoon@example.com"],
        expected_entities=["박지훈"],
    ),
    QAGoldenPair(
        id="T1-08", question="노트북 카테고리의 상위 카테고리는?",
        category="traverse", difficulty="easy",
        expected_keywords=["전자기기"],
        expected_entities=["노트북"],
    ),
    QAGoldenPair(
        id="T1-09", question="김민수의 위시리스트에 있는 상품은?",
        category="traverse", difficulty="medium",
        expected_keywords=["LG그램", "소니WH-1000XM5"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="T1-10", question="LG그램의 재고 수량은?",
        category="traverse", difficulty="easy",
        expected_keywords=["30"],
        expected_entities=["LG그램"],
    ),

    # ── traverse (2홉) — 8개 ────────────────────────────────────
    QAGoldenPair(
        id="T2-01", question="김민수가 주문한 상품은?",
        category="traverse", difficulty="medium",
        expected_keywords=["맥북프로", "에어팟프로", "갤럭시탭"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="T2-02", question="이영희가 주문한 상품 목록은?",
        category="traverse", difficulty="medium",
        expected_keywords=["LG그램", "갤럭시버즈", "맥북프로", "소니WH-1000XM5"],
        expected_entities=["이영희"],
    ),
    QAGoldenPair(
        id="T2-03", question="박지훈이 주문한 상품은 무엇인가요?",
        category="traverse", difficulty="medium",
        expected_keywords=["아이패드에어", "맥북프로"],
        expected_entities=["박지훈"],
    ),
    QAGoldenPair(
        id="T2-04", question="정대현이 구매한 상품은?",
        category="traverse", difficulty="medium",
        expected_keywords=["에어팟프로", "LG그램"],
        expected_entities=["정대현"],
    ),
    QAGoldenPair(
        id="T2-05", question="최수진이 주문한 상품은?",
        category="traverse", difficulty="medium",
        expected_keywords=["맥북에어"],
        expected_entities=["최수진"],
    ),
    QAGoldenPair(
        id="T2-06", question="김민수 주문의 배송 상태는?",
        category="traverse", difficulty="medium",
        expected_keywords=["delivered"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="T2-07", question="이영희 주문의 결제 방법은?",
        category="traverse", difficulty="medium",
        expected_keywords=["bank_transfer", "credit_card"],
        expected_entities=["이영희"],
    ),
    QAGoldenPair(
        id="T2-08", question="맥북프로를 주문한 고객은?",
        category="traverse", difficulty="medium",
        expected_keywords=["김민수", "이영희", "박지훈"],
        expected_entities=["맥북프로"],
    ),

    # ── traverse (3홉) — 4개 ────────────────────────────────────
    QAGoldenPair(
        id="T3-01", question="김민수가 주문한 상품의 카테고리는?",
        category="traverse", difficulty="hard",
        expected_keywords=["노트북", "오디오", "태블릿"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="T3-02", question="박지훈이 주문한 상품의 공급업체는?",
        category="traverse", difficulty="hard",
        expected_keywords=["애플코리아"],
        expected_entities=["박지훈"],
    ),
    QAGoldenPair(
        id="T3-03", question="이영희가 주문한 상품의 카테고리는?",
        category="traverse", difficulty="hard",
        expected_keywords=["노트북", "오디오"],
        expected_entities=["이영희"],
    ),
    QAGoldenPair(
        id="T3-04", question="정대현이 구매한 상품의 공급업체는?",
        category="traverse", difficulty="hard",
        expected_keywords=["애플코리아", "LG전자"],
        expected_entities=["정대현"],
    ),

    # ── aggregate — 10개 ────────────────────────────────────────
    QAGoldenPair(
        id="A-01", question="가장 많이 팔린 카테고리 Top 3는?",
        category="aggregate", difficulty="medium",
        expected_keywords=["노트북", "오디오"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-02", question="고객별 주문 수는?",
        category="aggregate", difficulty="medium",
        expected_keywords=["김민수", "이영희"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-03", question="전체 주문의 평균 금액은?",
        category="aggregate", difficulty="medium",
        expected_keywords=["평균"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-04", question="상품별 리뷰 평점 Top 3는?",
        category="aggregate", difficulty="medium",
        expected_keywords=["맥북에어", "에어팟프로"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-05", question="카테고리별 주문 건수를 알려주세요",
        category="aggregate", difficulty="medium",
        expected_keywords=["노트북", "오디오", "태블릿"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-06", question="총 고객 수는 몇 명인가요?",
        category="aggregate", difficulty="easy",
        expected_keywords=["5"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-07", question="총 주문 건수는 몇 건인가요?",
        category="aggregate", difficulty="easy",
        expected_keywords=["8"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-08", question="가장 비싼 상품은?",
        category="aggregate", difficulty="easy",
        expected_keywords=["맥북프로", "3500000"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-09", question="총 상품 수는 몇 개인가요?",
        category="aggregate", difficulty="easy",
        expected_keywords=["8"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="A-10", question="카테고리별 상품 수는?",
        category="aggregate", difficulty="medium",
        expected_keywords=["노트북", "오디오", "태블릿"],
        expected_entities=[],
    ),

    # ── comparison — 8개 ────────────────────────────────────────
    QAGoldenPair(
        id="C-01", question="김민수와 이영희가 공통으로 구매한 상품은?",
        category="comparison", difficulty="hard",
        expected_keywords=["맥북프로"],
        expected_entities=["김민수", "이영희"],
    ),
    QAGoldenPair(
        id="C-02", question="쿠폰 사용 주문과 미사용 주문의 평균 금액 비교",
        category="comparison", difficulty="hard",
        expected_keywords=["쿠폰"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="C-03", question="김민수와 박지훈이 공통으로 구매한 상품은?",
        category="comparison", difficulty="hard",
        expected_keywords=["맥북프로"],
        expected_entities=["김민수", "박지훈"],
    ),
    QAGoldenPair(
        id="C-04", question="리뷰 평점 Top 3 상품은?",
        category="comparison", difficulty="medium",
        expected_keywords=["맥북에어", "에어팟프로", "아이패드에어"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="C-05", question="노트북과 오디오 카테고리 중 어느 쪽이 더 많이 팔렸나요?",
        category="comparison", difficulty="medium",
        expected_keywords=["노트북", "오디오"],
        expected_entities=["노트북", "오디오"],
    ),
    QAGoldenPair(
        id="C-06", question="애플코리아와 삼성전자 공급 상품 비교",
        category="comparison", difficulty="medium",
        expected_keywords=["맥북프로", "갤럭시탭"],
        expected_entities=["애플코리아", "삼성전자"],
    ),
    QAGoldenPair(
        id="C-07", question="이영희와 정대현이 공통 구매한 상품은?",
        category="comparison", difficulty="hard",
        expected_keywords=["LG그램"],
        expected_entities=["이영희", "정대현"],
    ),
    QAGoldenPair(
        id="C-08", question="credit_card와 bank_transfer 결제 비교",
        category="comparison", difficulty="medium",
        expected_keywords=["credit_card", "bank_transfer"],
        expected_entities=[],
    ),

    # ── complex — 5개 ──────────────────────────────────────────
    QAGoldenPair(
        id="X-01", question="배송 상태별 주문 건수는?",
        category="complex", difficulty="hard",
        expected_keywords=["delivered", "in_transit"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="X-02", question="결제 방법별 통계를 알려주세요",
        category="complex", difficulty="hard",
        expected_keywords=["credit_card", "bank_transfer", "kakaopay"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="X-03", question="김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?",
        category="complex", difficulty="hard",
        expected_keywords=["맥북에어", "에어팟프로", "아이패드에어"],
        expected_entities=["김민수"],
    ),
    QAGoldenPair(
        id="X-04", question="WELCOME10 쿠폰을 사용한 주문은?",
        category="complex", difficulty="medium",
        expected_keywords=["WELCOME10"],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="X-05", question="서울시에 거주하는 고객은?",
        category="complex", difficulty="medium",
        expected_keywords=["김민수", "이영희"],
        expected_entities=[],
    ),

    # ── unsupported — 5개 ──────────────────────────────────────
    QAGoldenPair(
        id="U-01", question="반품 정책은 어떻게 되나요?",
        category="unsupported", difficulty="easy",
        expected_keywords=[],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-02", question="오늘 날씨 어때?",
        category="unsupported", difficulty="easy",
        expected_keywords=[],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-03", question="좋은 영화 추천해줘",
        category="unsupported", difficulty="easy",
        expected_keywords=[],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-04", question="Python으로 퀵소트 코드 작성해줘",
        category="unsupported", difficulty="easy",
        expected_keywords=[],
        expected_entities=[],
    ),
    QAGoldenPair(
        id="U-05", question="최근 뉴스 알려줘",
        category="unsupported", difficulty="easy",
        expected_keywords=[],
        expected_entities=[],
    ),
]
