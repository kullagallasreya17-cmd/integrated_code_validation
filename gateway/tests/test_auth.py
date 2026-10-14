from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionFactory
from app.config import settings
from app.models import UserRecord
from sqlalchemy import select


def test_signup_login_logout_and_password_hash():
    email = f"auth-test-{uuid4().hex}@example.test"
    with TestClient(app, base_url="https://testserver") as client:
        registered = client.post("/api/auth/register", json={
            "email": email,
            "full_name": "Auth Test User",
            "password": "correct-horse-battery-42",
        })
        assert registered.status_code == 201
        assert registered.json()["user"]["role"] == "Developer"
        assert "cva_session" in registered.headers.get("set-cookie", "")
        assert client.get("/api/auth/me").json()["user"]["email"] == email

        user_id = registered.json()["user"]["id"]
        with TestClient(app, base_url="https://testserver") as anonymous_client:
            denied = anonymous_client.get("/api/projects")
            assert denied.status_code == 401

        logged_out = client.post("/api/auth/logout")
        assert logged_out.status_code == 204
        assert client.get("/api/auth/me").status_code == 401

    import asyncio

    async def read_password_hash():
        async with SessionFactory() as session:
            return await session.scalar(select(UserRecord.password_hash).where(UserRecord.user_id == user_id))

    stored_hash = asyncio.run(read_password_hash())
    assert stored_hash is not None
    assert stored_hash != "correct-horse-battery-42"
    assert stored_hash.startswith("$argon2")


def test_duplicate_registration_and_invalid_login_are_rejected():
    email = f"duplicate-test-{uuid4().hex}@example.test"
    with TestClient(app, base_url="https://testserver") as client:
        body = {"email": email, "full_name": "Duplicate User", "password": "correct-horse-battery-42"}
        assert client.post("/api/auth/register", json=body).status_code == 201
        assert client.post("/api/auth/register", json=body).status_code == 409
        assert client.post("/api/auth/login", json={"email": email, "password": "not-the-password"}).status_code == 401


def test_projects_are_isolated_by_owner():
    with TestClient(app, base_url="https://testserver") as owner, TestClient(app, base_url="https://testserver") as other:
        owner_signup = owner.post("/api/auth/register", json={
            "email": f"owner-{uuid4().hex}@example.test",
            "full_name": "Project Owner",
            "password": "correct-horse-battery-42",
        })
        other_signup = other.post("/api/auth/register", json={
            "email": f"other-{uuid4().hex}@example.test",
            "full_name": "Other User",
            "password": "correct-horse-battery-42",
        })
        assert owner_signup.status_code == other_signup.status_code == 201
        created = owner.post("/api/projects", json={
            "name": "private project",
            "files": [{"path": "main.py", "content": "print('private')\n"}],
        })
        assert created.status_code == 200
        project_id = created.json()["project_id"]
        assert other.get(f"/api/projects/{project_id}").status_code == 404
        assert other.get("/api/projects").json()["total"] == 0


def test_bootstrap_admin_can_manage_users_and_developer_cannot(monkeypatch):
    admin_email = f"bootstrap-{uuid4().hex}@example.test"
    monkeypatch.setattr(settings, "bootstrap_admin_email", admin_email)
    monkeypatch.setattr(settings, "bootstrap_admin_password", "bootstrap-password-long-42")
    with TestClient(app, base_url="https://testserver") as admin_client:
        admin_login = admin_client.post("/api/auth/login", json={
            "email": admin_email,
            "password": "bootstrap-password-long-42",
            "remember": True,
        })
        assert admin_login.status_code == 200
        assert admin_login.json()["user"]["role"] == "Administrator"

        created = admin_client.post("/api/admin/users", json={
            "full_name": "Review Lead",
            "email": f"lead-{uuid4().hex}@example.test",
            "role": "Technical Lead",
            "password": "temporary-password-long-42",
        })
        assert created.status_code == 201
        assert created.json()["role"] == "Technical Lead"
        assert "password" not in created.json()
        assert "password_hash" not in created.json()

        developer_email = f"developer-{uuid4().hex}@example.test"
        with TestClient(app, base_url="https://testserver") as developer_client:
            assert developer_client.post("/api/auth/register", json={
                "email": developer_email,
                "full_name": "Regular Developer",
                "password": "developer-password-long-42",
            }).status_code == 201
            assert developer_client.get("/api/admin/users").status_code == 403