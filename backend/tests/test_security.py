"""Security and RBAC tests."""

from app.core.security import Role, has_permission, has_role_level, hash_password, verify_password


def test_password_hashing():
    password = "securepassword123"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)


def test_rbac_permissions():
    assert has_permission(Role.SUPER_ADMIN, "org:create")
    assert has_permission(Role.ORG_ADMIN, "workspace:create")
    assert not has_permission(Role.EMPLOYEE, "user:delete")
    assert has_permission(Role.EMPLOYEE, "chat:create")


def test_role_hierarchy():
    assert has_role_level(Role.SUPER_ADMIN, Role.ORG_ADMIN)
    assert has_role_level(Role.MANAGER, Role.EMPLOYEE)
    assert not has_role_level(Role.EMPLOYEE, Role.MANAGER)
