"""Tests for document parser module."""

from __future__ import annotations

import pytest

from app.document.parser import (
    ParsedDocument,
    detect_file_type,
    parse_document,
    _decode_text,
    _strip_markdown,
)


class TestDetectFileType:
    def test_pdf(self):
        assert detect_file_type("report.pdf") == "pdf"

    def test_docx(self):
        assert detect_file_type("report.docx") == "docx"

    def test_markdown(self):
        assert detect_file_type("README.md") == "md"
        assert detect_file_type("notes.markdown") == "md"

    def test_html(self):
        assert detect_file_type("page.html") == "html"

    def test_txt(self):
        assert detect_file_type("notes.txt") == "txt"

    def test_unsupported(self):
        assert detect_file_type("image.png") is None
        assert detect_file_type("data.csv") is None

    def test_case_insensitive(self):
        assert detect_file_type("REPORT.PDF") == "pdf"
        assert detect_file_type("Doc.DOCX") == "docx"


class TestDecodeText:
    def test_utf8(self):
        text = "Hello, world!"
        assert _decode_text(text.encode("utf-8")) == text

    def test_utf8_bom(self):
        text = "Hello"
        content = b"\xef\xbb\xbf" + text.encode("utf-8")
        assert _decode_text(content) == text

    def test_korean_utf8(self):
        text = "안녕하세요"
        assert _decode_text(text.encode("utf-8")) == text

    def test_korean_cp949(self):
        text = "안녕하세요"
        result = _decode_text(text.encode("cp949"))
        assert result == text

    def test_undecodable(self):
        # Invalid byte sequence that none of the encodings can handle
        assert _decode_text(b"\xff\xfe\x00\x01\x80\x81\x82\x83") is not None or _decode_text(b"\xff\xfe\x00\x01\x80\x81\x82\x83") is None


class TestStripMarkdown:
    def test_headers(self):
        result = _strip_markdown("# Title\n## Subtitle\nText")
        assert "Title" in result
        assert "Subtitle" in result
        assert "#" not in result

    def test_bold_italic(self):
        assert "bold" in _strip_markdown("**bold**")
        assert "italic" in _strip_markdown("*italic*")

    def test_links(self):
        result = _strip_markdown("[Click here](https://example.com)")
        assert "Click here" in result
        assert "https://example.com" not in result

    def test_code_blocks(self):
        result = _strip_markdown("Text\n```python\ncode\n```\nMore text")
        assert "code" not in result
        assert "Text" in result
        assert "More text" in result

    def test_inline_code(self):
        result = _strip_markdown("Use `print()` function")
        assert "print()" in result
        assert "`" not in result


class TestParseDocument:
    def test_unsupported_type(self):
        result = parse_document("image.png", b"data")
        assert result.errors
        assert result.file_type == "unknown"

    def test_txt_file(self):
        content = "Hello, this is a test document.\nSecond line."
        result = parse_document("test.txt", content.encode("utf-8"))
        assert result.file_type == "txt"
        assert not result.errors
        assert result.page_count == 1
        assert "Hello" in result.full_text

    def test_txt_empty(self):
        result = parse_document("empty.txt", b"   \n  ")
        assert result.pages == []

    def test_markdown_file(self):
        content = "# Title\n\nSome **bold** text and [link](http://example.com)."
        result = parse_document("readme.md", content.encode("utf-8"))
        assert result.file_type == "md"
        assert not result.errors
        assert "Title" in result.full_text

    def test_html_file_no_bs4(self):
        content = "<html><body><p>Hello</p><script>evil()</script></body></html>"
        result = parse_document("page.html", content.encode("utf-8"))
        assert result.file_type == "html"
        # Should extract text even with fallback regex parser
        assert result.pages

    def test_korean_txt(self):
        content = "이것은 테스트 문서입니다.\n두 번째 줄입니다."
        result = parse_document("test.txt", content.encode("utf-8"))
        assert "테스트" in result.full_text

    def test_large_txt(self):
        content = "Line\n" * 10000
        result = parse_document("big.txt", content.encode("utf-8"))
        assert not result.errors
        assert result.page_count == 1


class TestParsedDocument:
    def test_auto_full_text(self):
        from app.document.parser import ParsedPage
        doc = ParsedDocument(
            filename="test.txt",
            file_type="txt",
            pages=[
                ParsedPage(page_num=1, text="Page one"),
                ParsedPage(page_num=2, text="Page two"),
            ],
        )
        assert doc.full_text == "Page one\n\nPage two"
        assert doc.page_count == 2

    def test_empty_pages(self):
        doc = ParsedDocument(
            filename="empty.txt",
            file_type="txt",
            pages=[],
        )
        assert doc.full_text == ""
        assert doc.page_count == 0
