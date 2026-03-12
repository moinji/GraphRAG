"""Tests for document-to-KG linker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from app.document.linker import LinkingResult, link_document_to_kg, unlink_document_from_kg
from app.document.ner import ExtractedEntity


# ── LinkingResult dataclass ─────────────────────────────────────

class TestLinkingResult:
    def test_defaults(self):
        r = LinkingResult(document_id=1)
        assert r.document_node_created is False
        assert r.chunk_nodes_created == 0
        assert r.mentions_created == 0
        assert r.entities_found == 0
        assert r.errors == []


# ── link_document_to_kg ────────────────────────────────────────

class TestLinkDocumentToKG:
    def test_empty_chunks(self):
        """No chunks → immediate return."""
        result = link_document_to_kg(document_id=1, chunks=[])
        assert result.chunk_nodes_created == 0
        assert result.errors == []

    @patch("app.document.linker.get_driver", side_effect=Exception("Neo4j down"))
    def test_neo4j_unavailable(self, mock_driver):
        result = link_document_to_kg(
            document_id=1,
            chunks=[{"text": "hello", "chunk_index": 0, "metadata": {}}],
        )
        assert len(result.errors) == 1
        assert "Neo4j connection failed" in result.errors[0]

    @patch("app.document.linker.extract_entities", return_value=[])
    @patch("app.document.linker._get_document_meta", return_value=None)
    @patch("app.document.linker.get_driver")
    def test_document_not_in_pg(self, mock_driver, mock_meta, mock_ner):
        """Document not found in PG → error."""
        result = link_document_to_kg(
            document_id=999,
            chunks=[{"text": "hello", "chunk_index": 0, "metadata": {}}],
        )
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    @patch("app.document.linker.extract_entities", return_value=[])
    @patch("app.document.linker._get_document_meta")
    @patch("app.document.linker.get_driver")
    def test_creates_document_and_chunk_nodes(self, mock_get_driver, mock_meta, mock_ner):
        """Creates Document node and Chunk nodes in Neo4j."""
        mock_meta.return_value = {"filename": "test.pdf", "file_type": "pdf"}

        mock_session = MagicMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver

        result = link_document_to_kg(
            document_id=1,
            chunks=[
                {"text": "chunk one", "chunk_index": 0, "metadata": {"page_num": 1}},
                {"text": "chunk two", "chunk_index": 1, "metadata": {"page_num": 1}},
            ],
        )

        assert result.document_node_created is True
        assert result.chunk_nodes_created == 2
        assert result.errors == []

    @patch("app.document.linker.extract_entities")
    @patch("app.document.linker._get_document_meta")
    @patch("app.document.linker.get_driver")
    def test_creates_mentions_for_entities(self, mock_get_driver, mock_meta, mock_ner):
        """Creates MENTIONS relationships for matched entities."""
        mock_meta.return_value = {"filename": "test.pdf", "file_type": "pdf"}

        mock_session = MagicMock()
        # MENTIONS query returns count=1
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: 1
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver

        mock_ner.return_value = [
            ExtractedEntity("Alice", "Customer", 1.0, "kg_match", 0, 5),
        ]

        result = link_document_to_kg(
            document_id=1,
            chunks=[{"text": "Alice bought stuff", "chunk_index": 0, "metadata": {}}],
        )

        assert result.mentions_created >= 1
        assert result.entities_found >= 1

    @patch("app.document.linker.extract_entities")
    @patch("app.document.linker._get_document_meta")
    @patch("app.document.linker.get_driver")
    def test_low_confidence_filtered(self, mock_get_driver, mock_meta, mock_ner):
        """Entities below confidence threshold are not linked."""
        mock_meta.return_value = {"filename": "test.pdf", "file_type": "pdf"}

        mock_session = MagicMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver

        mock_ner.return_value = [
            ExtractedEntity("Maybe", "Unknown", 0.2, "llm"),
        ]

        result = link_document_to_kg(
            document_id=1,
            chunks=[{"text": "Maybe entity", "chunk_index": 0, "metadata": {}}],
            confidence_threshold=0.5,
        )

        # No MENTIONS should be created for low-confidence entity
        assert result.mentions_created == 0

    @patch("app.document.linker.extract_entities")
    @patch("app.document.linker._get_document_meta")
    @patch("app.document.linker.get_driver")
    def test_mentions_failure_non_fatal(self, mock_get_driver, mock_meta, mock_ner):
        """MENTIONS creation failure is non-fatal."""
        mock_meta.return_value = {"filename": "test.pdf", "file_type": "pdf"}

        mock_session = MagicMock()
        call_count = [0]

        def run_side_effect(*args, **kwargs):
            call_count[0] += 1
            cypher = args[0] if args else ""
            if "MENTIONS" in cypher:
                raise Exception("Match failed")
            return MagicMock()

        mock_session.run.side_effect = run_side_effect

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver

        mock_ner.return_value = [
            ExtractedEntity("Alice", "Customer", 1.0, "kg_match"),
        ]

        result = link_document_to_kg(
            document_id=1,
            chunks=[{"text": "Alice text", "chunk_index": 0, "metadata": {}}],
        )

        # Should complete without error
        assert result.document_node_created is True
        assert result.chunk_nodes_created == 1

    @patch("app.document.linker.extract_entities")
    @patch("app.document.linker._get_document_meta")
    @patch("app.document.linker.get_driver")
    def test_tenant_isolation(self, mock_get_driver, mock_meta, mock_ner):
        """Tenant ID is passed through."""
        mock_meta.return_value = {"filename": "test.pdf", "file_type": "pdf"}

        mock_session = MagicMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver
        mock_ner.return_value = []

        result = link_document_to_kg(
            document_id=1,
            chunks=[{"text": "hello", "chunk_index": 0, "metadata": {}}],
            tenant_id="tenant_A",
        )

        assert result.document_node_created is True
        # Verify tenant_id was passed to meta check and NER
        mock_meta.assert_called_once_with(1, "tenant_A")
        mock_ner.assert_called_once_with("hello", tenant_id="tenant_A")


# ── unlink_document_from_kg ────────────────────────────────────

class TestUnlinkDocumentFromKG:
    @patch("app.document.linker.get_driver")
    def test_unlink_success(self, mock_get_driver):
        mock_session = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: 5
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver

        count = unlink_document_from_kg(document_id=1)
        assert count == 5

    @patch("app.document.linker.get_driver", side_effect=Exception("Neo4j down"))
    def test_unlink_neo4j_failure(self, mock_driver):
        count = unlink_document_from_kg(document_id=1)
        assert count == 0

    @patch("app.document.linker.get_driver")
    def test_unlink_no_result(self, mock_get_driver):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_driver.return_value = mock_driver

        count = unlink_document_from_kg(document_id=999)
        assert count == 0
