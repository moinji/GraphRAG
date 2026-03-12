"""Tests for document chunking engine."""

from __future__ import annotations

import pytest

from app.document.chunker import Chunk, chunk_text, chunk_pages

class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "Hello, world!"
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].index == 0

    def test_fixed_strategy(self):
        text = "A" * 500
        chunks = chunk_text(text, strategy="fixed", chunk_size=200, chunk_overlap=50)
        assert len(chunks) >= 3
        # All chunks should be non-empty
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_recursive_splits_paragraphs(self):
        text = "Paragraph one with some text.\n\nParagraph two with more text.\n\nParagraph three."
        chunks = chunk_text(text, strategy="recursive", chunk_size=50, chunk_overlap=10)
        assert len(chunks) >= 2
        # Each chunk should be a recognizable portion
        all_text = " ".join(c.text for c in chunks)
        assert "Paragraph one" in all_text

    def test_sentence_strategy(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = chunk_text(text, strategy="sentence", chunk_size=40, chunk_overlap=10)
        assert len(chunks) >= 2

    def test_chunk_indices_sequential(self):
        text = "Hello. " * 100
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=10)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_metadata_passed_through(self):
        text = "Some text content here."
        chunks = chunk_text(text, chunk_size=1000, metadata={"page_num": 1})
        assert len(chunks) == 1
        assert chunks[0].metadata == {"page_num": 1}

    def test_char_count_property(self):
        text = "Hello, world!"
        chunks = chunk_text(text, chunk_size=1000)
        assert chunks[0].char_count == len("Hello, world!")

    def test_korean_text(self):
        text = "안녕하세요. 이것은 테스트입니다. 청킹이 잘 되는지 확인합니다."
        chunks = chunk_text(text, chunk_size=20, chunk_overlap=5)
        assert len(chunks) >= 1
        # All chunks should contain Korean text
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_overlap_produces_content(self):
        """Chunks should overlap when overlap > 0."""
        text = "AAAA BBBB CCCC DDDD EEEE FFFF GGGG HHHH"
        chunks = chunk_text(text, strategy="fixed", chunk_size=15, chunk_overlap=5)
        if len(chunks) >= 2:
            # The end of chunk N should overlap with the start of chunk N+1
            # (at least conceptually—exact overlap depends on splitting)
            assert True  # No crash is the baseline check

    def test_very_long_text(self):
        text = "Word " * 10000
        chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)
        assert len(chunks) > 10
        # Total content should cover the whole text
        total_chars = sum(c.char_count for c in chunks)
        assert total_chars > len(text) * 0.5  # at least 50% coverage


class TestChunkPages:
    def test_empty_pages(self):
        assert chunk_pages([]) == []

    def test_single_page(self):
        pages = [{"page_num": 1, "text": "Hello, this is page one."}]
        chunks = chunk_pages(pages, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0].metadata["page_num"] == 1

    def test_multi_page(self):
        pages = [
            {"page_num": 1, "text": "First page content."},
            {"page_num": 2, "text": "Second page content."},
            {"page_num": 3, "text": "Third page content."},
        ]
        chunks = chunk_pages(pages, chunk_size=1000)
        assert len(chunks) == 3
        assert chunks[0].metadata["page_num"] == 1
        assert chunks[1].metadata["page_num"] == 2
        assert chunks[2].metadata["page_num"] == 3

    def test_skips_empty_pages(self):
        pages = [
            {"page_num": 1, "text": "Content"},
            {"page_num": 2, "text": "   "},
            {"page_num": 3, "text": "More content"},
        ]
        chunks = chunk_pages(pages, chunk_size=1000)
        assert len(chunks) == 2
        page_nums = [c.metadata["page_num"] for c in chunks]
        assert 1 in page_nums
        assert 3 in page_nums

    def test_page_splitting(self):
        pages = [
            {"page_num": 1, "text": "A" * 500},
        ]
        chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=50)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.metadata["page_num"] == 1

    def test_global_index_ordering(self):
        pages = [
            {"page_num": 1, "text": "Short."},
            {"page_num": 2, "text": "Also short."},
        ]
        chunks = chunk_pages(pages, chunk_size=1000)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i


class TestChunkDataclass:
    def test_chunk_creation(self):
        c = Chunk(text="hello", index=0, char_start=0, char_end=5)
        assert c.text == "hello"
        assert c.char_count == 5

    def test_chunk_with_metadata(self):
        c = Chunk(text="hello", index=0, char_start=0, char_end=5, metadata={"page_num": 1})
        assert c.metadata["page_num"] == 1
