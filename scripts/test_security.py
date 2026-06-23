"""Security smoke tests for DataViz Agent.

Run this script after starting both services:

    Enterprise RAG auth service: http://localhost:8000/api/v1
    DataViz Agent service:      http://localhost:8001/api

Usage:
    python scripts/test_security.py
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass

import requests


AUTH_BASE_URL = "http://localhost:8000/api/v1"
AGENT_BASE_URL = "http://localhost:8001/api"


@dataclass
class UserSession:
    username: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[OK] {message}")


def unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def register_and_login(username: str) -> UserSession:
    password = "Passw0rd_123"
    register_resp = requests.post(
        f"{AUTH_BASE_URL}/auth/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    expect(
        register_resp.status_code in {201, 400},
        f"register {username} returns {register_resp.status_code}",
    )

    login_resp = requests.post(
        f"{AUTH_BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    expect(login_resp.status_code == 200, f"login {username} succeeds")
    return UserSession(username=username, token=login_resp.json()["access_token"])


def upload_csv(user: UserSession) -> str:
    files = {
        "file": (
            "security.csv",
            io.BytesIO(b"name,value\nA,1\nB,2\n"),
            "text/csv",
        )
    }
    resp = requests.post(
        f"{AGENT_BASE_URL}/upload",
        headers=user.headers,
        files=files,
        timeout=20,
    )
    expect(resp.status_code == 200, "user can upload own CSV")
    return resp.json()["file_path"]


def test_thread_ownership(user_a: UserSession, user_b: UserSession, file_path: str) -> None:
    thread_a = f"user_{user_a.username}_{uuid.uuid4().hex[:12]}"
    resp_a = requests.post(
        f"{AGENT_BASE_URL}/chat",
        headers=user_a.headers,
        json={"message": "看一下有哪些字段", "file_path": file_path, "thread_id": thread_a},
        timeout=60,
    )
    expect(resp_a.status_code == 200, "user A can create own agent thread")

    resp_b = requests.get(
        f"{AGENT_BASE_URL}/history/{thread_a}",
        headers=user_b.headers,
        timeout=10,
    )
    expect(resp_b.status_code == 403, "user B cannot read user A agent thread")


def test_file_path_isolation(user_b: UserSession, file_path_a: str) -> None:
    thread_b = f"user_{user_b.username}_{uuid.uuid4().hex[:12]}"
    resp = requests.post(
        f"{AGENT_BASE_URL}/chat",
        headers=user_b.headers,
        json={
            "message": "尝试越权读取文件",
            "file_path": file_path_a,
            "thread_id": thread_b,
        },
        timeout=20,
    )
    expect(resp.status_code == 403, "user B cannot use user A upload path")


def test_path_traversal_blocked(user_a: UserSession) -> None:
    thread = f"user_{user_a.username}_{uuid.uuid4().hex[:12]}"
    traversal_path = f"data/uploads/{user_a.username}/../other_user/fake.csv"
    resp = requests.post(
        f"{AGENT_BASE_URL}/chat",
        headers=user_a.headers,
        json={
            "message": "路径穿越测试",
            "file_path": traversal_path,
            "thread_id": thread,
        },
        timeout=20,
    )
    expect(resp.status_code == 403, "path traversal file path is blocked")


def main() -> None:
    print("[Security] DataViz Agent smoke tests")
    user_a = register_and_login(unique_username("agent_a"))
    user_b = register_and_login(unique_username("agent_b"))
    file_path_a = upload_csv(user_a)
    test_thread_ownership(user_a, user_b, file_path_a)
    test_file_path_isolation(user_b, file_path_a)
    test_path_traversal_blocked(user_a)
    print("[Security] all checks completed")


if __name__ == "__main__":
    main()
