"""Authentication service."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    Role,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import RefreshToken, User
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


class AuthService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._user_repo = UserRepository(session)
        self._token_repo = RefreshTokenRepository(session)
        self._settings = get_settings()

    async def register(self, request: RegisterRequest) -> TokenResponse:
        existing = await self._user_repo.get_by_email(request.email)
        if existing:
            raise ConflictError("Email already registered")

        org_id = None
        role = Role.EMPLOYEE

        if request.organization_name:
            org = Organization(
                id=uuid4(),
                name=request.organization_name,
                slug=request.organization_name.lower().replace(" ", "-")[:100],
            )
            self._session.add(org)
            await self._session.flush()
            org_id = org.id
            role = Role.ORG_ADMIN

        user = User(
            id=uuid4(),
            email=request.email,
            hashed_password=hash_password(request.password),
            full_name=request.full_name,
            role=role.value,
            organization_id=org_id,
        )
        await self._user_repo.create(user)
        return await self._generate_tokens(user)

    async def login(self, request: LoginRequest) -> TokenResponse:
        user = await self._user_repo.get_by_email(request.email)
        if not user or not verify_password(request.password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("Account is deactivated")

        user.last_login_at = datetime.now(UTC)
        await self._user_repo.update(user)
        return await self._generate_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except ValueError as e:
            raise UnauthorizedError(str(e)) from e

        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")

        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        stored = await self._token_repo.get_by_hash(token_hash)
        if not stored or stored.expires_at < datetime.now(UTC):
            raise UnauthorizedError("Invalid or expired refresh token")

        user = await self._user_repo.get_by_id(UUID(payload["sub"]))
        if not user or not user.is_active:
            raise UnauthorizedError("User not found")

        stored.is_revoked = True
        return await self._generate_tokens(user)

    async def logout(self, user_id: UUID) -> None:
        await self._token_repo.revoke_all_for_user(user_id)

    async def get_current_user_info(self, user_id: UUID) -> UserResponse:
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise UnauthorizedError("User not found")
        return UserResponse.model_validate(user)

    async def _generate_tokens(self, user: User) -> TokenResponse:
        access = create_access_token(user.id, Role(user.role), user.organization_id)
        refresh = create_refresh_token(user.id)

        token_hash = hashlib.sha256(refresh.encode()).hexdigest()
        refresh_entity = RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
        )
        await self._token_repo.create(refresh_entity)

        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )
