"""Reranker interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RankedResult:
    id: str
    content: str
    score: float
    metadata: dict


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[RankedResult],
        top_k: int = 5,
    ) -> list[RankedResult]:
        pass
