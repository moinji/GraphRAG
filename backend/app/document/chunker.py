"""Text chunking engine for document processing.

Strategies:
- recursive: Split by paragraph -> sentence -> character boundaries (default)
- fixed: Fixed character-length chunks with overlap
- sentence: Sentence-level chunking

All strategies respect chunk_size (in characters) and overlap.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Sentence boundary regex (Korean + English)
_SENTENCE_RE = re.compile(
    r"(?<=[.!?\u3002\uFF01\uFF1F])\s+|"  # After .!? (EN + CJK punctuation)
    r"(?<=\n)\s*"                           # After newline
)

# Paragraph boundary
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    """A single chunk of document text."""
    text: str
    index: int
    char_start: int
    char_end: int
    metadata: dict = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)


def chunk_text(
    text: str,
    strategy: str = "recursive",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split text into chunks using the specified strategy.

    Args:
        text: The full document text to chunk.
        strategy: "recursive" (default), "fixed", or "sentence".
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks in characters.
        metadata: Optional metadata to attach to each chunk (e.g. page_num).

    Returns:
        List of Chunk objects.
    """
    if not text or not text.strip():
        return []

    base_meta = metadata or {}

    if strategy == "fixed":
        raw_chunks = _fixed_chunks(text, chunk_size, chunk_overlap)
    elif strategy == "sentence":
        raw_chunks = _sentence_chunks(text, chunk_size, chunk_overlap)
    else:
        raw_chunks = _recursive_chunks(text, chunk_size, chunk_overlap)

    chunks: list[Chunk] = []
    for i, (chunk_text_str, char_start, char_end) in enumerate(raw_chunks):
        if chunk_text_str.strip():
            chunks.append(Chunk(
                text=chunk_text_str.strip(),
                index=i,
                char_start=char_start,
                char_end=char_end,
                metadata={**base_meta},
            ))

    return chunks


def chunk_pages(
    pages: list[dict],
    strategy: str = "recursive",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Chunk]:
    """Chunk multiple pages, preserving page_num metadata.

    Args:
        pages: List of {"page_num": int, "text": str} dicts.
        strategy: Chunking strategy.
        chunk_size: Target chunk size.
        chunk_overlap: Overlap between chunks.

    Returns:
        List of Chunk objects with page_num in metadata.
    """
    all_chunks: list[Chunk] = []
    global_offset = 0

    for page in pages:
        page_num = page.get("page_num", 0)
        page_text = page.get("text", "")
        if not page_text.strip():
            global_offset += len(page_text) + 2  # account for page separator
            continue

        page_chunks = chunk_text(
            page_text,
            strategy=strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            metadata={"page_num": page_num},
        )

        # Adjust indices to be global
        for chunk in page_chunks:
            chunk.index = len(all_chunks)
            chunk.char_start += global_offset
            chunk.char_end += global_offset
            all_chunks.append(chunk)

        global_offset += len(page_text) + 2

    return all_chunks


def _recursive_chunks(
    text: str, chunk_size: int, overlap: int,
) -> list[tuple[str, int, int]]:
    """Recursively split text: paragraphs -> sentences -> characters."""
    if len(text) <= chunk_size:
        return [(text, 0, len(text))]

    # Try splitting by paragraphs first
    paragraphs = _PARAGRAPH_RE.split(text)
    if len(paragraphs) > 1:
        return _merge_splits(paragraphs, text, chunk_size, overlap)

    # Then by sentences
    sentences = _SENTENCE_RE.split(text)
    if len(sentences) > 1:
        return _merge_splits(sentences, text, chunk_size, overlap)

    # Fall back to fixed-size splitting
    return _fixed_chunks(text, chunk_size, overlap)


def _merge_splits(
    splits: list[str],
    original_text: str,
    chunk_size: int,
    overlap: int,
) -> list[tuple[str, int, int]]:
    """Merge small splits into chunks that respect chunk_size."""
    chunks: list[tuple[str, int, int]] = []
    current_parts: list[str] = []
    current_len = 0
    current_start = 0
    char_pos = 0

    for split in splits:
        # Find the actual position in the original text
        split_start = original_text.find(split, char_pos)
        if split_start == -1:
            split_start = char_pos

        if current_len + len(split) > chunk_size and current_parts:
            # Flush current chunk
            chunk_text_str = "\n\n".join(current_parts)
            chunks.append((chunk_text_str, current_start, current_start + len(chunk_text_str)))

            # Handle overlap: keep last part(s) that fit within overlap
            overlap_parts: list[str] = []
            overlap_len = 0
            for part in reversed(current_parts):
                if overlap_len + len(part) <= overlap:
                    overlap_parts.insert(0, part)
                    overlap_len += len(part)
                else:
                    break

            current_parts = overlap_parts
            current_len = overlap_len
            if overlap_parts:
                # Find start of overlap in original text
                first_overlap = overlap_parts[0]
                overlap_start = original_text.find(first_overlap, current_start)
                if overlap_start != -1:
                    current_start = overlap_start
                else:
                    current_start = split_start
            else:
                current_start = split_start

        if not current_parts:
            current_start = split_start

        current_parts.append(split)
        current_len += len(split)
        char_pos = split_start + len(split)

    # Flush remaining
    if current_parts:
        chunk_text_str = "\n\n".join(current_parts)
        chunks.append((chunk_text_str, current_start, current_start + len(chunk_text_str)))

    return chunks


def _fixed_chunks(
    text: str, chunk_size: int, overlap: int,
) -> list[tuple[str, int, int]]:
    """Split text into fixed-size character chunks with overlap."""
    chunks: list[tuple[str, int, int]] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append((text[start:end], start, end))
        if end >= text_len:
            break
        start = end - overlap

    return chunks


def _sentence_chunks(
    text: str, chunk_size: int, overlap: int,
) -> list[tuple[str, int, int]]:
    """Split text into sentence-boundary-respecting chunks."""
    sentences = _SENTENCE_RE.split(text)
    if not sentences:
        return [(text, 0, len(text))]

    return _merge_splits(sentences, text, chunk_size, overlap)
