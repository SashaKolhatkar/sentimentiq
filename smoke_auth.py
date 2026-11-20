"""Multi-user auth smoke test. Run from the project root with `python smoke_auth.py`."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["SENTIMENTIQ_AUTH_ENABLED"] = "true"
os.environ["SENTIMENTIQ_SECRET_KEY"] = "smoke-test-secret"
os.environ["SENTIMENTIQ_ADMIN_USER"] = "admin"
os.environ["SENTIMENTIQ_ADMIN_PASSWORD"] = "AdminPass123!"

from fastapi.testclient import TestClient

from backend.app import config, db

TEST_DB = Path(tempfile.mkdtemp(prefix="sentimentiq_auth_")) / "test.db"
config.DB_PATH = TEST_DB
db.DB_PATH = TEST_DB

from backend.app.main import app


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("PASS " if condition else "FAIL ") + label + (f" :: {detail[:300]}" if detail else ""))
    if not condition:
        raise AssertionError(label)


def main() -> None:
    with TestClient(app) as client:
        check("auth enabled", client.get("/api/health").json()["auth_enabled"] is True)
        check("registration closed after seed", client.get("/api/config").json()["registration_open"] is False)

        admin = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass123!"})
        check("admin login", admin.status_code == 200)
        admin_user = admin.json()["user"]
        admin_headers = {"Authorization": f"Bearer {admin.json()['token']}"}
        check("admin role", admin_user["role"] == "admin")
        check("me endpoint", client.get("/api/auth/me", headers=admin_headers).json()["id"] == admin_user["id"])
        check("bad password rejected", client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401)

        analyst = client.post("/api/users", headers=admin_headers, json={
            "username": "analyst1", "email": "analyst@example.com",
            "password": "AnalystPass123!", "role": "analyst",
        })
        check("create analyst", analyst.status_code == 200, analyst.text)
        analyst_id = analyst.json()["user"]["id"]
        analyst_login = client.post("/api/auth/login", json={"username": "analyst1", "password": "AnalystPass123!"})
        analyst_headers = {"Authorization": f"Bearer {analyst_login.json()['token']}"}
        check("analyst login", analyst_login.status_code == 200)

        viewer = client.post("/api/users", headers=admin_headers, json={
            "username": "viewer1", "password": "ViewerPass123!", "role": "viewer",
        })
        check("create viewer", viewer.status_code == 200, viewer.text)
        viewer_id = viewer.json()["user"]["id"]
        viewer_login = client.post("/api/auth/login", json={"username": "viewer1", "password": "ViewerPass123!"})
        viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['token']}"}
        check("viewer cannot write", client.post("/api/analyze", headers=viewer_headers, json={}).status_code == 403)
        check("analyst passes write check", client.post("/api/analyze", headers=analyst_headers, json={}).status_code == 422)

        changed = client.post("/api/auth/password", headers=analyst_headers, json={
            "current_password": "AnalystPass123!", "new_password": "NewAnalystPass123!",
        })
        check("change own password", changed.status_code == 200, changed.text)
        check("old password rejected", client.post("/api/auth/login", json={"username": "analyst1", "password": "AnalystPass123!"}).status_code == 401)
        check("new password works", client.post("/api/auth/login", json={"username": "analyst1", "password": "NewAnalystPass123!"}).status_code == 200)

        reset = client.post(f"/api/users/{analyst_id}/password", headers=admin_headers, json={"new_password": "ResetPass123!"})
        check("admin reset password", reset.status_code == 200, reset.text)
        check("reset password works", client.post("/api/auth/login", json={"username": "analyst1", "password": "ResetPass123!"}).status_code == 200)

        disabled = client.patch(f"/api/users/{viewer_id}", headers=admin_headers, json={"disabled": True})
        check("disable account", disabled.status_code == 200 and disabled.json()["user"]["disabled"] is True, disabled.text)
        check("disabled cannot login", client.post("/api/auth/login", json={"username": "viewer1", "password": "ViewerPass123!"}).status_code == 401)
        check("enable account", client.patch(f"/api/users/{viewer_id}", headers=admin_headers, json={"disabled": False}).status_code == 200)
        check("non-admin cannot list users", client.get("/api/users", headers=analyst_headers).status_code == 403)
        check("last admin protected", client.patch(f"/api/users/{admin_user['id']}", headers=admin_headers, json={"role": "viewer"}).status_code == 400)
        check("delete user", client.delete(f"/api/users/{viewer_id}", headers=admin_headers).status_code == 200)
        check("self-delete blocked", client.delete(f"/api/users/{admin_user['id']}", headers=admin_headers).status_code == 400)

    print("ALL PASS")


if __name__ == "__main__":
    main()
