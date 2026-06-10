"""Text chunking strategies: fixed, recursive, semantic."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    page_number: int | None
    token_count: int


class BaseChunker(ABC):
    @abstractmethod
    def chunk(
        self,
        text: str,
        page_number: int | None = None,
        start_index: int = 0,
    ) -> list[TextChunk]:
        pass


class FixedChunker(BaseChunker):
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(
        self,
        text: str,
        page_number: int | None = None,
        start_index: int = 0,
    ) -> list[TextChunk]:
        chunks = []
        step = self._chunk_size - self._overlap
        for i, start in enumerate(range(0, len(text), step)):
            content = text[start : start + self._chunk_size].strip()
            if content:
                chunks.append(TextChunk(
                    content=content,
                    chunk_index=start_index + i,
                    page_number=page_number,
                    token_count=len(content.split()),
                ))
        return chunks


class RecursiveChunker(BaseChunker):
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk(
        self,
        text: str,
        page_number: int | None = None,
        start_index: int = 0,
    ) -> list[TextChunk]:
        splits = self._splitter.split_text(text)
        return [
            TextChunk(
                content=content,
                chunk_index=start_index + i,
                page_number=page_number,
                token_count=len(content.split()),
            )
            for i, content in enumerate(splits)
            if content.strip()
        ]


class SemanticChunker(BaseChunker):
    """Semantic chunking using paragraph boundaries with size limits."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self._max_size = chunk_size
        self._overlap = overlap
        self._fallback = RecursiveChunker(chunk_size, overlap)

    def chunk(
        self,
        text: str,
        page_number: int | None = None,
        start_index: int = 0,
    ) -> list[TextChunk]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        idx = start_index

        for para in paragraphs:
            if len(current) + len(para) > self._max_size and current:
                chunks.append(TextChunk(
                    content=current.strip(),
                    chunk_index=idx,
                    page_number=page_number,
                    token_count=len(current.split()),
                ))
                idx += 1
                overlap_text = current[-self._overlap:] if len(current) > self._overlap else ""
                current = overlap_text + " " + para
            else:
                current = f"{current}\n\n{para}" if current else para

        if current.strip():
            chunks.append(TextChunk(
                content=current.strip(),
                chunk_index=idx,
                page_number=page_number,
                token_count=len(current.split()),
            ))

        if not chunks:
            return self._fallback.chunk(text, page_number, start_index)
        return chunks


def get_chunker(strategy: str, chunk_size: int = 512, overlap: int = 64) -> BaseChunker:
    chunkers = {
        "fixed": FixedChunker,
        "recursive": RecursiveChunker,
        "semantic": SemanticChunker,
    }
    chunker_class = chunkers.get(strategy, RecursiveChunker)
    return chunker_class(chunk_size, overlap)
