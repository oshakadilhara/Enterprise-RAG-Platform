"""Security utilities: JWT, password hashing, RBAC."""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.SUPER_ADMIN: 100,
    Role.ORG_ADMIN: 80,
    Role.MANAGER: 50,
    Role.EMPLOYEE: 10,
}

PERMISSIONS: dict[Role, set[str]] = {
    Role.SUPER_ADMIN: {
        "org:create", "org:read", "org:update", "org:delete",
        "user:create", "user:read", "user:update", "user:delete",
        "workspace:create", "workspace:read", "workspace:update", "workspace:delete",
        "document:create", "document:read", "document:update", "document:delete",
        "chat:create", "chat:read", "analytics:read", "evaluation:run",
        "settings:manage",
    },
    Role.ORG_ADMIN: {
        "org:read", "org:update",
        "user:create", "user:read", "user:update", "user:delete",
        "workspace:create", "workspace:read", "workspace:update", "workspace:delete",
        "document:create", "document:read", "document:update", "document:delete",
        "chat:create", "chat:read", "analytics:read", "evaluation:run",
        "settings:manage",
    },
    Role.MANAGER: {
        "user:read",
        "workspace:create", "workspace:read", "workspace:update",
        "document:create", "document:read", "document:update", "document:delete",
        "chat:create", "chat:read", "analytics:read",
    },
    Role.EMPLOYEE: {
        "workspace:read",
        "document:read",
        "chat:create", "chat:read",
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str | UUID,
    role: Role,
    organization_id: str | UUID | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role.value,
        "exp": expire,
        "type": "access",
    }
    if organization_id:
        payload["org_id"] = str(organization_id)
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str | UUID) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


def has_permission(role: Role, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def has_role_level(user_role: Role, required_role: Role) -> bool:
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)
