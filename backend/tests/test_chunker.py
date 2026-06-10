"""Chunking strategy tests."""

from app.services.ingestion.chunker import FixedChunker, RecursiveChunker, SemanticChunker


def test_fixed_chunker():
    chunker = FixedChunker(chunk_size=50, overlap=10)
    text = "A" * 200
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    assert all(len(c.content) <= 50 for c in chunks)


def test_recursive_chunker():
    chunker = RecursiveChunker(chunk_size=100, overlap=20)
    text = "Paragraph one.\n\nParagraph two with more content.\n\nParagraph three."
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1
    assert all(c.content.strip() for c in chunks)


def test_semantic_chunker():
    chunker = SemanticChunker(chunk_size=100, overlap=10)
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1
