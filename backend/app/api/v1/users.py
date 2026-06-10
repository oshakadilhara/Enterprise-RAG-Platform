"""User management API."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUserDep, DbSession
from app.core.exceptions import NotFoundError
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserResponse
from app.schemas.common import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    current_user: CurrentUserDep,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    current_user.require_permission("user:read")
    repo = UserRepository(db)
    users, total = await repo.list_by_organization(
        current_user.organization_id, page, page_size
    )
    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("user:read")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User", str(user_id))
    return UserResponse.model_validate(user)
