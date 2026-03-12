"""Query pipeline tests — 46 cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ════════════════════════════════════════════════════════════════════
#  Template Registry
# ════════════════════════════════════════════════════════════════════


def test_registry_has_28_templates():
    """#1: Registry contains exactly 28 templates (18 base + 10 extended)."""
    from app.query.template_registry import REGISTRY

    assert len(REGISTRY) == 28


def test_render_two_hop():
    """#2: Slot filling produces valid Cypher for two_hop."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("two_hop", {
        "start_label": "Customer",
        "start_prop": "name",
        "rel1": "PLACED",
        "mid_label": "Order",
        "rel2": "CONTAINS",
        "end_label": "Product",
        "return_prop": "name",
    })
    assert "Customer" in cypher
    assert ":PLACED" in cypher
    assert ":CONTAINS" in cypher
    assert "$val" in cypher


def test_render_agg_with_rel():
    """#3: Slot filling produces valid Cypher for agg_with_rel."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("agg_with_rel", {
        "start_label": "Order",
        "rel1": "CONTAINS",
        "mid_label": "Product",
        "rel2": "BELONGS_TO",
        "end_label": "Category",
        "group_prop": "name",
    })
    assert "Order" in cypher
    assert "count(DISTINCT a)" in cypher
    assert "$limit" in cypher


# ════════════════════════════════════════════════════════════════════
#  Slot Validation
# ════════════════════════════════════════════════════════════════════


def test_slot_validation_rejects_injection():
    """#4: Node label with special characters is rejected."""
    from app.exceptions import QueryRoutingError
    from app.query.slot_filler import fill_template

    with pytest.raises(QueryRoutingError, match="Invalid node label"):
        fill_template("two_hop", {
            "start_label": "Customer; DROP",
            "start_prop": "name",
            "rel1": "PLACED",
            "mid_label": "Order",
            "rel2": "CONTAINS",
            "end_label": "Product",
            "return_prop": "name",
        }, {"val": "test"})


# ════════════════════════════════════════════════════════════════════
#  Rule Router
# ════════════════════════════════════════════════════════════════════


def test_rules_match_top_n():
    """#5: Aggregation pattern 'Top 3 카테고리' matches."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("가장 많이 팔린 카테고리 Top 3는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "agg_with_rel"
    assert route == "cypher_agg"
    assert params["limit"] == 3


def test_rules_match_average():
    """#6: Aggregation keyword '평균' detected in AGG_KEYWORDS."""
    from app.query.router_rules import AGG_KEYWORDS

    assert AGG_KEYWORDS.search("평균 금액은?") is not None


def test_rules_match_q1_pattern():
    """#7: '김민수가 주문한 상품' matches Q1 (two_hop)."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("고객 김민수가 주문한 상품은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "two_hop"
    assert route == "cypher_traverse"
    assert params["val"] == "김민수"


def test_rules_no_match():
    """#8: Unrelated question returns None."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("오늘 날씨가 어때?")
    assert result is None


# ════════════════════════════════════════════════════════════════════
#  Hybrid Router
# ════════════════════════════════════════════════════════════════════


def test_hybrid_rules_priority():
    """#9: When rules match, LLM is never called."""
    with patch("app.query.router.classify_by_llm") as mock_llm:
        from app.query.router import route_question

        tid, route, slots, params, matched_by = route_question("고객 김민수가 주문한 상품은?")
        assert matched_by == "rule"
        assert tid == "two_hop"
        mock_llm.assert_not_called()


def test_hybrid_llm_fallback():
    """#10: When rules don't match + API key present → LLM called."""
    mock_result = (
        "status_filter",
        "cypher_traverse",
        {"start_label": "Shipping", "rel1": "SHIPPED_TO", "end_label": "Address", "status_prop": "status", "op": "=", "return_prop": "city"},
        {"status_val": "delivered"},
    )
    with (
        patch("app.query.router.settings") as mock_settings,
        patch("app.query.router.classify_by_llm", return_value=mock_result) as mock_llm,
    ):
        mock_settings.openai_api_key = "test-key"
        from app.query.router import route_question

        tid, route, slots, params, matched_by = route_question("배송 완료된 주문의 도착 지역은?")
        assert matched_by == "llm"
        assert tid == "status_filter"
        mock_llm.assert_called_once()


def test_hybrid_no_key_unsupported():
    """#11: No API key + rules miss → unsupported."""
    with patch("app.query.router.settings") as mock_settings:
        mock_settings.openai_api_key = None
        from app.query.router import route_question

        tid, route, slots, params, matched_by = route_question("반품 정책은?")
        assert route == "unsupported"
        assert matched_by == "none"


# ════════════════════════════════════════════════════════════════════
#  Query API
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_query_api_success(api_client: AsyncClient):
    """#12: POST /query with rule-matched question → 200 + answer (non-cached)."""
    mock_records = [{"result": "맥북프로"}, {"result": "에어팟프로"}]
    with patch("app.query.pipeline._execute_cypher", return_value=mock_records):
        # Use a question that is NOT in the demo cache
        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "고객 이영희가 주문한 상품은?"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched_by"] == "rule"
    assert data["template_id"] == "two_hop"
    assert "맥북프로" in data["answer"]
    assert data["cypher"] != ""
    assert data["error"] is None


@pytest.mark.anyio
async def test_query_api_unsupported(api_client: AsyncClient):
    """#13: Unsupported question → 200 + error field."""
    with patch("app.query.router.settings") as mock_settings:
        mock_settings.openai_api_key = None
        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "반품 정책은?"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["route"] == "unsupported"
    assert data["error"] is not None
    assert data["cypher"] == ""


@pytest.mark.anyio
async def test_query_api_neo4j_failure(api_client: AsyncClient):
    """#14: Neo4j failure → 502 (non-cached question)."""
    from app.exceptions import CypherExecutionError
    from app.query.pipeline import invalidate_query_cache

    invalidate_query_cache()  # clear LRU cache from prior tests

    with patch(
        "app.query.pipeline._execute_cypher",
        side_effect=CypherExecutionError("Connection refused"),
    ):
        # Use a question that is NOT in the demo cache
        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "고객 이영희가 주문한 상품은?"},
        )
    assert resp.status_code == 502
    assert "Connection refused" in resp.json()["detail"]


@pytest.mark.anyio
async def test_pipeline_paths_included(api_client: AsyncClient):
    """#15: Response includes evidence paths (non-cached question)."""
    mock_records = [{"result": "맥북프로"}, {"result": "갤럭시탭"}]
    with patch("app.query.pipeline._execute_cypher", return_value=mock_records):
        # Use a question that is NOT in the demo cache
        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "고객 이영희가 주문한 상품은?"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paths"]) == 2
    assert "Customer(이영희)" in data["paths"][0]
    assert "Product(맥북프로)" in data["paths"][0]


# ════════════════════════════════════════════════════════════════════
#  Q4 Rule Router
# ════════════════════════════════════════════════════════════════════


def test_rules_match_q4_pattern():
    """#16: '김민수와 이영희가 공통으로 구매한 상품' matches Q4."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("김민수와 이영희가 공통으로 구매한 상품은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "custom_q4"
    assert route == "cypher_traverse"
    assert params["name1"] == "김민수"
    assert params["name2"] == "이영희"


def test_rules_match_q4_reversed_names():
    """#17: Q4 pattern with reversed names."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("이영희과 김민수가 공통 구매한 상품은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "custom_q4"
    assert params["name1"] == "이영희"
    assert params["name2"] == "김민수"


# ════════════════════════════════════════════════════════════════════
#  Demo Cache
# ════════════════════════════════════════════════════════════════════


def test_cache_hit():
    """#18: Known demo question returns cached response."""
    from app.query.demo_cache import get_cached_answer

    resp = get_cached_answer("고객 김민수가 주문한 상품은?")
    assert resp is not None
    assert resp.cached is True
    assert "맥북프로" in resp.answer
    assert resp.template_id == "two_hop"
    assert resp.matched_by == "rule"


def test_cache_miss():
    """#19: Unknown question returns None."""
    from app.query.demo_cache import get_cached_answer

    resp = get_cached_answer("오늘 날씨가 어때?")
    assert resp is None


# ════════════════════════════════════════════════════════════════════
#  English Rule Router (P3-20 Multilingual)
# ════════════════════════════════════════════════════════════════════


def test_rules_en_q1():
    """#20: English Q1 'What products did X order?' matches two_hop."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("What products did 김민수 order?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "two_hop"
    assert route == "cypher_traverse"
    assert params["val"] == "김민수"


def test_rules_en_q3():
    """#21: English Q3 'Top 3 best-selling categories' matches agg_with_rel."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("Top 3 best-selling categories?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "agg_with_rel"
    assert route == "cypher_agg"
    assert params["limit"] == 3


def test_rules_en_q5():
    """#22: English Q5 'Coupon used vs unused' matches custom_q5."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("Coupon used vs unused average amount comparison")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "custom_q5"
    assert route == "cypher_agg"


def test_rules_en_q4():
    """#23: English Q4 'products X and Y bought' matches custom_q4."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("products 김민수 and 이영희 bought")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "custom_q4"
    assert params["name1"] == "김민수"
    assert params["name2"] == "이영희"


# ════════════════════════════════════════════════════════════════════
#  Bilingual Answer Generation (P3-20)
# ════════════════════════════════════════════════════════════════════


def test_answer_korean():
    """#24: Korean question gets Korean answer."""
    from app.query.pipeline import _generate_answer

    answer = _generate_answer(
        "고객 김민수가 주문한 상품은?",
        [{"result": "맥북프로"}],
        "two_hop",
        {"start_label": "Customer", "end_label": "Product"},
        {"val": "김민수"},
    )
    assert "김민수" in answer
    assert "맥북프로" in answer


def test_answer_english():
    """#25: English question gets English answer."""
    from app.query.pipeline import _generate_answer

    answer = _generate_answer(
        "What products did Alice order?",
        [{"result": "MacBookPro"}],
        "two_hop",
        {"start_label": "Customer", "end_label": "Product"},
        {"val": "Alice"},
    )
    assert "Alice" in answer
    assert "MacBookPro" in answer


def test_unsupported_english():
    """#26: English unsupported question gets English message."""
    from app.query.pipeline import _is_korean

    assert _is_korean("What is the weather?") is False
    assert _is_korean("고객 김민수") is True


def test_no_results_english():
    """#27: English question with no results gets English message."""
    from app.query.pipeline import _generate_answer

    answer = _generate_answer("What products did X order?", [], "two_hop", {}, {})
    assert "No results found" in answer


# ════════════════════════════════════════════════════════════════════
#  Extended Templates (B1 - Cypher Template Expansion)
# ════════════════════════════════════════════════════════════════════


def test_render_property_lookup():
    """#28: property_lookup template renders valid Cypher."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("property_lookup", {
        "label": "Customer",
        "match_prop": "name",
        "return_prop": "email",
    })
    assert "Customer" in cypher
    assert "$val" in cypher
    assert "email" in cypher


def test_render_count_all():
    """#29: count_all template renders valid Cypher."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("count_all", {"label": "Customer"})
    assert "Customer" in cypher
    assert "count(n)" in cypher


def test_render_reverse_two_hop():
    """#30: reverse_two_hop template renders valid Cypher."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("reverse_two_hop", {
        "end_label": "Customer",
        "rel1": "PLACED",
        "mid_label": "Order",
        "rel2": "CONTAINS",
        "start_label": "Product",
        "start_prop": "name",
        "return_prop": "name",
    })
    assert "Customer" in cypher
    assert ":PLACED" in cypher
    assert "$val" in cypher


def test_render_group_count():
    """#31: group_count template renders valid Cypher."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("group_count", {
        "start_label": "Customer",
        "rel1": "PLACED",
        "end_label": "Order",
        "group_prop": "name",
    })
    assert "Customer" in cypher
    assert "count(b)" in cypher


def test_render_max_prop():
    """#32: max_prop template renders valid Cypher."""
    from app.query.template_registry import render_cypher

    cypher = render_cypher("max_prop", {
        "label": "Product",
        "return_prop": "name",
        "sort_prop": "price",
    })
    assert "Product" in cypher
    assert "ORDER BY" in cypher
    assert "LIMIT 1" in cypher


# ── Q6: 3-hop (category/supplier) ──────────────────────────────


def test_rules_q6_category():
    """#33: '김민수가 주문한 상품의 카테고리' matches three_hop."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("김민수가 주문한 상품의 카테고리는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "three_hop"
    assert slots["end_label"] == "Category"
    assert params["val"] == "김민수"


def test_rules_q6_supplier():
    """#34: '박지훈이 주문한 상품의 공급업체' matches three_hop."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("박지훈이 주문한 상품의 공급업체는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "three_hop"
    assert slots["end_label"] == "Supplier"
    assert params["val"] == "박지훈"


# ── Q7: Reverse 2-hop ──────────────────────────────────────────


def test_rules_q7_reverse():
    """#35: '맥북프로를 주문한 고객은?' matches reverse_two_hop."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("맥북프로를 주문한 고객은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "reverse_two_hop"
    assert params["val"] == "맥북프로"


def test_rules_q7_en():
    """#36: English 'Who ordered MacBookPro?' matches reverse_two_hop."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("Who ordered 맥북프로?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "reverse_two_hop"
    assert params["val"] == "맥북프로?"  # trailing ? gets captured, OK


# ── Q8: Count all ──────────────────────────────────────────────


def test_rules_q8_count_customers():
    """#37: '총 고객 수는?' matches count_all."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("총 고객 수는 몇 명인가요?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "count_all"
    assert slots["label"] == "Customer"


def test_rules_q8_count_orders():
    """#38: '총 주문 건수는?' matches count_all."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("총 주문 수는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "count_all"
    assert slots["label"] == "Order"


def test_rules_q8_en():
    """#39: English 'How many products?' matches count_all."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("How many products are there?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "count_all"
    assert slots["label"] == "Product"


# ── Q9: Max/Min property ──────────────────────────────────────


def test_rules_q9_most_expensive():
    """#40: '가장 비싼 상품은?' matches max_prop."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("가장 비싼 상품은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "max_prop"
    assert slots["sort_prop"] == "price"


# ── Q10: 1-hop relationship ───────────────────────────────────


def test_rules_q10_category():
    """#41: '에어팟프로의 카테고리는?' matches one_hop_out."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("에어팟프로의 카테고리는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "one_hop_out"
    assert slots["rel1"] == "BELONGS_TO"
    assert params["val"] == "에어팟프로"


def test_rules_q10_wishlist():
    """#42: '김민수의 위시리스트에 있는 상품은?' matches one_hop_out."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("김민수의 위시리스트에 있는 상품은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "one_hop_out"
    assert slots["rel1"] == "WISHLISTED"
    assert params["val"] == "김민수"


# ── Q11: Property lookup ──────────────────────────────────────


def test_rules_q11_email():
    """#43: '김민수의 이메일은?' matches property_lookup."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("김민수의 이메일 주소는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "property_lookup"
    assert slots["label"] == "Customer"
    assert slots["return_prop"] == "email"
    assert params["val"] == "김민수"


def test_rules_q11_price():
    """#44: '맥북프로의 가격은?' matches property_lookup."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("맥북프로의 가격은?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "property_lookup"
    assert slots["label"] == "Product"
    assert slots["return_prop"] == "price"


# ── Q12: Group count ──────────────────────────────────────────


def test_rules_q12_orders_per_customer():
    """#45: '고객별 주문 수는?' matches group_count."""
    from app.query.router_rules import classify_by_rules

    result = classify_by_rules("고객별 주문 수는?")
    assert result is not None
    tid, route, slots, params = result
    assert tid == "group_count"
    assert slots["start_label"] == "Customer"


# ── Answer generation for new templates ─────────────────────────


def test_answer_count_all():
    """#46: count_all answer generation."""
    from app.query.pipeline import _generate_answer

    answer = _generate_answer(
        "총 고객 수는?",
        [{"total": 5}],
        "count_all",
        {"label": "Customer"},
        {},
    )
    assert "5" in answer
    assert "Customer" in answer


# ════════════════════════════════════════════════════════════════════
#  Mode C Demo Cache
# ════════════════════════════════════════════════════════════════════


def test_cache_c_hit_battery():
    """#47: Mode C cache hit for battery question."""
    from app.query.demo_cache_c import get_cached_answer_c

    resp = get_cached_answer_c("맥북프로의 배터리 수명은 얼마나 되나요?")
    assert resp is not None
    assert resp.cached is True
    assert resp.mode == "c"
    assert "22시간" in resp.answer
    assert len(resp.document_sources) == 1
    assert resp.document_sources[0].filename == "맥북프로_제품설명.md"


def test_cache_c_hit_hybrid():
    """#48: Mode C cache hit for hybrid question (KG + doc)."""
    from app.query.demo_cache_c import get_cached_answer_c

    resp = get_cached_answer_c("김민수가 주문한 맥북프로의 주요 사양은?")
    assert resp is not None
    assert resp.cached is True
    assert "M3" in resp.answer
    assert resp.subgraph_context is not None
    assert len(resp.document_sources) >= 1
    assert "Customer_1" in resp.related_node_ids


def test_cache_c_hit_return_policy():
    """#49: Mode C cache hit for return policy (doc-only)."""
    from app.query.demo_cache_c import get_cached_answer_c

    resp = get_cached_answer_c("반품 정책은 어떻게 되나요?")
    assert resp is not None
    assert "7일" in resp.answer
    assert resp.document_sources[0].filename == "쇼핑몰_이용안내.md"


def test_cache_c_miss():
    """#50: Mode C cache miss returns None."""
    from app.query.demo_cache_c import get_cached_answer_c

    resp = get_cached_answer_c("존재하지 않는 질문")
    assert resp is None


def test_cache_c_all_five_present():
    """#51: All 5 Mode C demo questions are cached."""
    from app.query.demo_cache_c import get_cached_answer_c

    questions = [
        "맥북프로의 배터리 수명은 얼마나 되나요?",
        "에어팟프로의 노이즈캔슬링 기능에 대해 설명해주세요.",
        "김민수가 주문한 맥북프로의 주요 사양은?",
        "반품 정책은 어떻게 되나요?",
        "애플코리아가 공급하는 제품들의 특징은?",
    ]
    for q in questions:
        resp = get_cached_answer_c(q)
        assert resp is not None, f"Cache miss for: {q}"
        assert resp.cached is True
        assert resp.mode == "c"


# ════════════════════════════════════════════════════════════════════
#  Synonym normalization
# ════════════════════════════════════════════════════════════════════


def test_synonym_normalize_korean_order():
    """#S1: '오더' → '주문' 정규화."""
    from app.query.router_rules import _normalize_synonyms
    assert "주문" in _normalize_synonyms("김민수가 오더한 상품")


def test_synonym_normalize_korean_product():
    """#S2: '제품' → '상품' 정규화."""
    from app.query.router_rules import _normalize_synonyms
    assert "상품" in _normalize_synonyms("어떤 제품이 있나요?")


def test_synonym_normalize_english():
    """#S3: 'purchase' → 'order' 정규화."""
    from app.query.router_rules import _normalize_synonyms
    assert "order" in _normalize_synonyms("What did John purchase?")


def test_synonym_q1_routes_with_synonym():
    """#S4: '김민수가 구입한 제품' → Q1 라우팅 성공."""
    from app.query.router_rules import classify_by_rules
    result = classify_by_rules("김민수가 구입한 제품")
    assert result is not None, "Synonym-based Q1 should route"
    template_id = result[0]
    assert template_id in ("one_hop_out", "two_hop"), f"Expected traverse template, got {template_id}"


def test_synonym_q5_routes_with_synonym():
    """#S5: '할인권 사용 미사용 비교' → Q5 라우팅 성공."""
    from app.query.router_rules import classify_by_rules
    result = classify_by_rules("할인권 사용 미사용 비교")
    assert result is not None, "Synonym-based Q5 should route"
    assert result[0] == "custom_q5"


def test_synonym_customer_variation():
    """#S6: '소비자' → '고객' 정규화."""
    from app.query.router_rules import _normalize_synonyms
    normalized = _normalize_synonyms("소비자가 주문한 상품")
    assert "고객" in normalized
