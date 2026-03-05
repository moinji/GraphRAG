"""Graph API tests — 10 cases for stats, reset, full, neighbors endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


# ── Helpers ──────────────────────────────────────────────────────

def _mock_driver():
    """Create a mock Neo4j driver with session context."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def app():
    return create_app()


# ── GET /stats ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_graph_stats_success(app):
    driver, session = _mock_driver()
    node_rows = [{"lbl": "Customer", "cnt": 5}, {"lbl": "Product", "cnt": 8}]
    edge_rows = [{"t": "PLACED", "cnt": 10}]
    session.run.side_effect = [iter(node_rows), iter(edge_rows)]

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_nodes"] == 13
    assert data["total_edges"] == 10
    assert data["node_counts"]["Customer"] == 5


@pytest.mark.anyio
async def test_graph_stats_neo4j_down(app):
    driver, session = _mock_driver()
    session.run.side_effect = Exception("Connection refused")

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/stats")

    assert resp.status_code == 503


# ── DELETE /reset ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_graph_reset_success(app):
    driver, session = _mock_driver()
    counts_result = MagicMock()
    counts_result.__getitem__ = lambda self, k: {"node_cnt": 42, "edge_cnt": 55}[k]
    session.run.return_value.single.return_value = counts_result
    # second call (DETACH DELETE) returns nothing special
    session.run.side_effect = [MagicMock(single=MagicMock(return_value=counts_result)), MagicMock()]

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete("/api/v1/graph/reset")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted_nodes"] == 42
    assert data["deleted_edges"] == 55


@pytest.mark.anyio
async def test_graph_reset_neo4j_down(app):
    driver, session = _mock_driver()
    session.run.side_effect = Exception("Connection refused")

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete("/api/v1/graph/reset")

    assert resp.status_code == 503


# ── GET /full ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_graph_full_success(app):
    driver, session = _mock_driver()
    # Mock total counts, node records, edge records
    total_n = MagicMock(); total_n.__getitem__ = lambda self, k: 3
    total_e = MagicMock(); total_e.__getitem__ = lambda self, k: 2

    node1 = MagicMock()
    node1.__getitem__ = lambda self, k: {
        "n": {"id": 1, "name": "Kim"},
        "lbls": ["Customer"],
        "eid": "e1",
    }[k]

    session.run.side_effect = [
        MagicMock(single=MagicMock(return_value=total_n)),
        MagicMock(single=MagicMock(return_value=total_e)),
        iter([node1]),
        iter([]),  # edges
    ]

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/full?limit=100")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_nodes"] == 3


@pytest.mark.anyio
async def test_graph_full_neo4j_down(app):
    driver, session = _mock_driver()
    session.run.side_effect = Exception("Connection refused")

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/full")

    assert resp.status_code == 503


# ── GET /neighbors/{node_id} ───────────────────────────────────

@pytest.mark.anyio
async def test_graph_neighbors_bad_format(app):
    """node_id without underscore should 400."""
    with patch("app.routers.graph.get_driver"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/neighbors/InvalidId")

    assert resp.status_code == 400


@pytest.mark.anyio
async def test_graph_neighbors_not_found(app):
    driver, session = _mock_driver()
    session.run.return_value.single.return_value = None

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/neighbors/Customer_999")

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_graph_neighbors_neo4j_down(app):
    driver, session = _mock_driver()
    anchor_mock = MagicMock()
    anchor_mock.single.return_value = {"n": {}, "eid": "e1"}
    # First call ok, second raises
    session.run.side_effect = [anchor_mock, Exception("Connection refused")]

    with patch("app.routers.graph.get_driver", return_value=driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/graph/neighbors/Customer_1")

    assert resp.status_code == 503
