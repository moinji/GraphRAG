"""B안 Local Search tests — 15 cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# ── Seed entity data for tests (simulates Neo4j-loaded entities) ──
_SEED_ENTITIES: dict[str, set[str]] = {
    "Customer": {"김민수", "이영희", "박지훈", "최수진", "정대현"},
    "Product": {
        "맥북프로", "에어팟프로", "갤럭시탭", "LG그램", "갤럭시버즈",
        "아이패드에어", "맥북에어", "소니WH-1000XM5",
    },
    "Category": {"전자기기", "의류", "식품", "노트북", "오디오", "태블릿"},
    "Supplier": {"애플코리아", "삼성전자", "LG전자"},
}


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
#  Entity Extraction
# ════════════════════════════════════════════════════════════════════


def test_entity_extraction_customer():
    """#1: Customer name extracted correctly."""
    from app.query.local_search import extract_entity

    with patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES):
        name, label = extract_entity("김민수가 주문한 상품은?")
    assert name == "김민수"
    assert label == "Customer"


def test_entity_extraction_product():
    """#2: Product name extracted correctly."""
    from app.query.local_search import extract_entity

    with patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES):
        name, label = extract_entity("맥북프로의 가격은?")
    assert name == "맥북프로"
    assert label == "Product"


def test_entity_extraction_category():
    """#3: Category name extracted correctly."""
    from app.query.local_search import extract_entity

    with patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES):
        name, label = extract_entity("노트북 카테고리의 상위 카테고리는?")
    assert name == "노트북"
    assert label == "Category"


def test_entity_extraction_no_match():
    """#4: Unknown question returns None."""
    from app.query.local_search import extract_entity

    with patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES):
        name, label = extract_entity("오늘 날씨 어때?")
    assert name is None
    assert label is None


# ════════════════════════════════════════════════════════════════════
#  Depth Determination
# ════════════════════════════════════════════════════════════════════


def test_depth_default():
    """#5: Default question gets depth 2."""
    from app.query.local_search import determine_depth

    assert determine_depth("김민수가 주문한 상품은?") == 2


def test_depth_1hop():
    """#6: '직접 연결된' keyword gives depth 1."""
    from app.query.local_search import determine_depth

    assert determine_depth("직접 연결된 노드는?") == 1


def test_depth_3hop():
    """#7: '전체 구조' keyword gives depth 3."""
    from app.query.local_search import determine_depth

    assert determine_depth("전체 구조를 보여줘") == 3


# ════════════════════════════════════════════════════════════════════
#  Subgraph Cypher Generation
# ════════════════════════════════════════════════════════════════════


def test_subgraph_cypher_valid():
    """#8: Generated Cypher contains expected patterns."""
    from app.query.local_search import build_subgraph_cypher

    cypher = build_subgraph_cypher("Customer", 2)
    assert "MATCH (anchor:Customer" in cypher
    assert "$entity_name" in cypher
    assert "hop1" in cypher
    assert "hop2" in cypher


# ════════════════════════════════════════════════════════════════════
#  Serialization & Parsing
# ════════════════════════════════════════════════════════════════════


def test_serialize_subgraph():
    """#9: Subgraph serialization produces structured text."""
    from app.query.local_prompts import serialize_subgraph

    hop1 = [
        {"label": "Order", "name": "1", "rel": "PLACED", "props": {"status": "delivered"}},
        {"label": "Address", "name": "강남구", "rel": "LIVES_AT", "props": {}},
    ]
    hop2 = [
        {"label": "Product", "name": "맥북프로", "rel": "CONTAINS", "props": {"price": 3500000}},
    ]
    text = serialize_subgraph("Customer", "김민수", hop1, hop2)
    assert "[앵커 노드] Customer: 김민수" in text
    assert "[1홉 연결]" in text
    assert "PLACED" in text
    assert "[2홉 연결]" in text
    assert "맥북프로" in text


def test_parse_local_answer():
    """#10: Answer/paths parsing works correctly."""
    from app.query.local_prompts import parse_local_answer

    raw = "답변: 김민수가 주문한 상품은 맥북프로, 에어팟프로입니다.\n근거 경로: Customer(김민수)->PLACED->Order->CONTAINS->Product(맥북프로)\n- Customer(김민수)->PLACED->Order->CONTAINS->Product(에어팟프로)"
    answer, paths = parse_local_answer(raw)
    assert "맥북프로" in answer
    assert len(paths) >= 1


# ════════════════════════════════════════════════════════════════════
#  Full Pipeline (mocked)
# ════════════════════════════════════════════════════════════════════


def test_run_local_query_success():
    """#11: Full B안 pipeline with mocked Neo4j + LLM."""
    from app.query.local_search import run_local_query

    mock_neo4j_result = [{
        "anchor": MagicMock(),
        "anchor_label": "Customer",
        "hop1": [
            {"label": "Order", "name": "1", "rel": "PLACED", "props": {"status": "delivered"}},
        ],
        "hop2": [
            {"label": "Product", "name": "맥북프로", "rel": "CONTAINS", "props": {}},
        ],
    }]

    with (
        patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES),
        patch("app.query.local_search._execute_neo4j", return_value=mock_neo4j_result),
        patch(
            "app.query.local_search.generate_answer_with_llm",
            return_value=("김민수가 주문한 상품은 맥북프로입니다.", ["Customer(김민수)->Order->Product(맥북프로)"], 150),
        ),
    ):
        result = run_local_query("김민수가 주문한 상품은?")
    assert result.mode == "b"
    assert result.answer != ""
    assert result.route == "local_search"
    assert result.llm_tokens_used == 150


def test_run_local_query_no_entity():
    """#12: No entity → unsupported with error field."""
    from app.query.local_search import run_local_query

    with patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES):
        result = run_local_query("오늘 날씨 어때?")
    assert result.mode == "b"
    assert result.error is not None
    assert result.route == "unsupported"


def test_run_local_query_neo4j_fail():
    """#13: Neo4j failure → LocalSearchError (502)."""
    from app.exceptions import LocalSearchError
    from app.query.local_search import run_local_query

    with (
        patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES),
        patch(
            "app.query.local_search._execute_neo4j",
            side_effect=LocalSearchError("Connection refused"),
        ),
    ):
        with pytest.raises(LocalSearchError, match="Connection refused"):
            run_local_query("김민수가 주문한 상품은?")


def test_run_local_query_llm_fail():
    """#14: LLM failure → LocalSearchError (502)."""
    from app.exceptions import LocalSearchError
    from app.query.local_search import run_local_query

    mock_neo4j_result = [{
        "anchor": MagicMock(),
        "anchor_label": "Customer",
        "hop1": [{"label": "Order", "name": "1", "rel": "PLACED", "props": {}}],
        "hop2": [],
    }]

    with (
        patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES),
        patch("app.query.local_search._execute_neo4j", return_value=mock_neo4j_result),
        patch(
            "app.query.local_search.generate_answer_with_llm",
            side_effect=LocalSearchError("API rate limited"),
        ),
    ):
        with pytest.raises(LocalSearchError, match="API rate limited"):
            run_local_query("김민수가 주문한 상품은?")


# ════════════════════════════════════════════════════════════════════
#  API Integration
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_api_mode_b(api_client: AsyncClient):
    """#15: POST /query mode=b → 200 with B안 response."""
    mock_neo4j_result = [{
        "anchor": MagicMock(),
        "anchor_label": "Customer",
        "hop1": [{"label": "Order", "name": "1", "rel": "PLACED", "props": {}}],
        "hop2": [{"label": "Product", "name": "맥북프로", "rel": "CONTAINS", "props": {}}],
    }]

    with (
        patch("app.query.local_search._load_entities_from_neo4j", return_value=_SEED_ENTITIES),
        patch("app.query.local_search._execute_neo4j", return_value=mock_neo4j_result),
        patch(
            "app.query.local_search.generate_answer_with_llm",
            return_value=("맥북프로입니다.", ["path1"], 100),
        ),
    ):
        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "김민수가 주문한 상품은?", "mode": "b"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "b"
    assert data["route"] == "local_search"
    assert data["llm_tokens_used"] == 100
