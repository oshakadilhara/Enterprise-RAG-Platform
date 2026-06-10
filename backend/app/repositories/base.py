"""Base repository with common CRUD operations."""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]):
        self._session = session
        self._model = model

    async def get_by_id(self, id: UUID) -> ModelT | None:
        return await self._session.get(self._model, id)

    async def create(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
        await self._session.flush()

    async def count(self, **filters) -> int:
        query = select(func.count()).select_from(self._model)
        for key, value in filters.items():
            query = query.where(getattr(self._model, key) == value)
        result = await self._session.execute(query)
        return result.scalar() or 0
