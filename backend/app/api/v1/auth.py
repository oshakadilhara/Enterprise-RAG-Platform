"""Authentication API endpoints."""

from fastapi import APIRouter

from app.core.dependencies import CurrentUserDep, DbSession
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(request: RegisterRequest, db: DbSession):
    service = AuthService(db)
    return await service.register(request)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: DbSession):
    service = AuthService(db)
    return await service.login(request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: DbSession):
    service = AuthService(db)
    return await service.refresh(request.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: CurrentUserDep, db: DbSession):
    service = AuthService(db)
    await service.logout(current_user.id)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUserDep, db: DbSession):
    service = AuthService(db)
    return await service.get_current_user_info(current_user.id)
