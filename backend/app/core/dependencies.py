"""FastAPI dependency injection."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import Role, decode_token, has_permission
from app.models.user import User
from app.repositories.user_repository import UserRepository

security = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


class CurrentUser:
    def __init__(self, user: User, token_payload: dict):
        self.user = user
        self.token_payload = token_payload

    @property
    def id(self) -> UUID:
        return self.user.id

    @property
    def role(self) -> Role:
        return Role(self.user.role)

    @property
    def organization_id(self) -> UUID | None:
        return self.user.organization_id

    def require_permission(self, permission: str) -> None:
        if not has_permission(self.role, permission):
            raise ForbiddenError(f"Missing permission: {permission}")


async def get_current_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    if not credentials:
        raise UnauthorizedError("Authentication required")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError as e:
        raise UnauthorizedError(str(e)) from e

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    repo = UserRepository(db)
    user = await repo.get_by_id(UUID(user_id))
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return CurrentUser(user=user, token_payload=payload)


async def get_optional_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser | None:
    if not credentials:
        return None
    try:
        return await get_current_user(db, credentials)
    except UnauthorizedError:
        return None


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]


def require_permission(permission: str):
    async def checker(current_user: CurrentUserDep) -> CurrentUser:
        current_user.require_permission(permission)
        return current_user
    return checker


async def get_request_id(
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
) -> str | None:
    return x_request_id
