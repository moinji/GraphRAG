"""Tests for document upload API endpoints."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestDocumentUploadAPI:
    """Test POST /api/v1/documents/upload."""

    def test_upload_txt_file(self):
        """Upload a simple text file."""
        content = b"Hello, this is a test document."
        files = [("files", ("test.txt", io.BytesIO(content), "text/plain"))]

        with patch("app.routers.documents._process_document_task"):
            response = client.post("/api/v1/documents/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["total_queued"] == 1
        assert len(data["accepted"]) == 1
        assert data["accepted"][0]["filename"] == "test.txt"

    def test_upload_unsupported_type(self):
        """Reject unsupported file types."""
        files = [("files", ("image.png", io.BytesIO(b"data"), "image/png"))]

        response = client.post("/api/v1/documents/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["total_queued"] == 0
        assert len(data["errors"]) == 1
        assert "unsupported" in data["errors"][0].lower()

    def test_upload_empty_file(self):
        """Reject empty files."""
        files = [("files", ("empty.txt", io.BytesIO(b""), "text/plain"))]

        response = client.post("/api/v1/documents/upload", files=files)

        data = response.json()
        assert data["total_queued"] == 0
        assert len(data["errors"]) == 1

    def test_upload_multiple_files(self):
        """Upload multiple files at once."""
        files = [
            ("files", ("doc1.txt", io.BytesIO(b"Content 1"), "text/plain")),
            ("files", ("doc2.md", io.BytesIO(b"# Title\nContent"), "text/markdown")),
        ]

        with patch("app.routers.documents._process_document_task"):
            response = client.post("/api/v1/documents/upload", files=files)

        data = response.json()
        assert data["total_queued"] == 2

    def test_upload_mixed_valid_invalid(self):
        """Upload mix of valid and invalid files."""
        files = [
            ("files", ("valid.txt", io.BytesIO(b"Content"), "text/plain")),
            ("files", ("bad.exe", io.BytesIO(b"data"), "application/octet-stream")),
        ]

        with patch("app.routers.documents._process_document_task"):
            response = client.post("/api/v1/documents/upload", files=files)

        data = response.json()
        assert data["total_queued"] == 1
        assert len(data["errors"]) == 1

    def test_upload_pdf_extension_accepted(self):
        """PDF extension should be accepted (even if content isn't real PDF)."""
        files = [("files", ("report.pdf", io.BytesIO(b"fake pdf content"), "application/pdf"))]

        with patch("app.routers.documents._process_document_task"):
            response = client.post("/api/v1/documents/upload", files=files)

        data = response.json()
        assert data["total_queued"] == 1

    def test_upload_docx_extension_accepted(self):
        """DOCX extension should be accepted."""
        files = [("files", ("doc.docx", io.BytesIO(b"fake docx"), "application/vnd.openxmlformats"))]

        with patch("app.routers.documents._process_document_task"):
            response = client.post("/api/v1/documents/upload", files=files)

        data = response.json()
        assert data["total_queued"] == 1


class TestDocumentListAPI:
    """Test GET /api/v1/documents."""

    def test_list_empty(self):
        """List documents when none exist."""
        with patch("app.db.vector_store.list_documents", return_value=[]):
            response = client.get("/api/v1/documents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["documents"] == []

    def test_list_with_documents(self):
        """List documents when some exist."""
        mock_docs = [
            {
                "id": 1,
                "filename": "test.pdf",
                "file_type": "pdf",
                "file_size": 1024,
                "page_count": 5,
                "chunk_count": 10,
                "status": "ready",
                "created_at": "2026-03-10 12:00:00",
            },
        ]
        with patch("app.db.vector_store.list_documents", return_value=mock_docs):
            response = client.get("/api/v1/documents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["documents"][0]["filename"] == "test.pdf"


class TestDocumentGetAPI:
    """Test GET /api/v1/documents/{id}."""

    def test_get_existing(self):
        mock_doc = {
            "id": 1,
            "filename": "test.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "page_count": 5,
            "chunk_count": 10,
            "status": "ready",
            "created_at": "2026-03-10",
        }
        with patch("app.db.vector_store.get_document", return_value=mock_doc):
            response = client.get("/api/v1/documents/1")

        assert response.status_code == 200
        assert response.json()["filename"] == "test.pdf"

    def test_get_not_found(self):
        with patch("app.db.vector_store.get_document", return_value=None):
            response = client.get("/api/v1/documents/999")

        assert response.status_code == 404


class TestDocumentDeleteAPI:
    """Test DELETE /api/v1/documents/{id}."""

    def test_delete_existing(self):
        with patch("app.db.vector_store.delete_document", return_value=True):
            response = client.delete("/api/v1/documents/1")

        assert response.status_code == 200

    def test_delete_not_found(self):
        with patch("app.db.vector_store.delete_document", return_value=False):
            response = client.delete("/api/v1/documents/999")

        assert response.status_code == 404
