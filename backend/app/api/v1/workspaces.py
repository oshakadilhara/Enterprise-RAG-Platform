"""Workspace management API."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUserDep, DbSession, require_permission
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.workspace import Workspace, WorkspaceMember
from app.repositories.user_repository import UserRepository
from app.repositories.workspace_repository import WorkspaceMemberRepository, WorkspaceRepository
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberInvite,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)

router = APIRouter()


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    request: WorkspaceCreate,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("workspace:create")
    if not current_user.organization_id:
        raise ForbiddenError("User must belong to an organization")

    repo = WorkspaceRepository(db)
    workspace = Workspace(
        id=uuid4(),
        name=request.name,
        description=request.description,
        organization_id=current_user.organization_id,
        created_by=current_user.id,
        chunking_strategy=request.chunking_strategy,
    )
    workspace = await repo.create(workspace)

    member_repo = WorkspaceMemberRepository(db)
    await member_repo.create(WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=current_user.id,
        role="owner",
    ))

    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        organization_id=workspace.organization_id,
        created_by=workspace.created_by,
        chunking_strategy=workspace.chunking_strategy,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        member_count=1,
        document_count=0,
    )


@router.get("", response_model=PaginatedResponse[WorkspaceResponse])
async def list_workspaces(
    current_user: CurrentUserDep,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    current_user.require_permission("workspace:read")
    repo = WorkspaceRepository(db)
    workspaces, total = await repo.list_by_organization(
        current_user.organization_id, page, page_size
    )
    items = [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            description=ws.description,
            organization_id=ws.organization_id,
            created_by=ws.created_by,
            chunking_strategy=ws.chunking_strategy,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            member_count=len(ws.members),
            document_count=len(ws.documents),
        )
        for ws in workspaces
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    repo = WorkspaceRepository(db)
    ws = await repo.get_with_members(workspace_id)
    if not ws:
        raise NotFoundError("Workspace", str(workspace_id))
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        organization_id=ws.organization_id,
        created_by=ws.created_by,
        chunking_strategy=ws.chunking_strategy,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
        member_count=len(ws.members),
        document_count=len(ws.documents) if ws.documents else 0,
    )


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    request: WorkspaceUpdate,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("workspace:update")
    repo = WorkspaceRepository(db)
    ws = await repo.get_by_id(workspace_id)
    if not ws:
        raise NotFoundError("Workspace", str(workspace_id))

    if request.name is not None:
        ws.name = request.name
    if request.description is not None:
        ws.description = request.description
    if request.chunking_strategy is not None:
        ws.chunking_strategy = request.chunking_strategy

    ws = await repo.update(ws)
    return WorkspaceResponse.model_validate(ws)


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse, status_code=201)
async def invite_member(
    workspace_id: UUID,
    request: WorkspaceMemberInvite,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("workspace:update")
    user_repo = UserRepository(db)
    member_repo = WorkspaceMemberRepository(db)

    user = await user_repo.get_by_email(request.email)
    if not user:
        raise NotFoundError("User", request.email)

    existing = await member_repo.get_membership(workspace_id, user.id)
    if existing:
        raise ForbiddenError("User is already a member")

    member = await member_repo.create(WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace_id,
        user_id=user.id,
        role=request.role,
    ))

    return WorkspaceMemberResponse(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.joined_at,
    )


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
async def list_members(
    workspace_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    member_repo = WorkspaceMemberRepository(db)
    members = await member_repo.list_members(workspace_id)
    return [
        WorkspaceMemberResponse(
            id=m.id,
            user_id=m.user_id,
            email=m.user.email,
            full_name=m.user.full_name,
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in members
    ]
