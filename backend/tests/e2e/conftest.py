"""
Shared fixtures for e2e tests.
Tests run against the live Docker application at localhost:8081.
"""
import uuid
import pytest
import httpx

BASE_URL = "http://localhost:8081/api/v1"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def unique_email() -> str:
    return f"e2e_{uuid.uuid4().hex[:8]}@test.com"


@pytest.fixture(scope="session")
def user_password() -> str:
    return "TestPass123!"


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def registered_token(client: httpx.Client, unique_email: str, user_password: str) -> str:
    """Register a new user and return the access token."""
    resp = client.post("/auth/register", json={
        "email": unique_email,
        "password": user_password,
    })
    assert resp.status_code == 201, f"Register failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(registered_token: str) -> dict:
    return {"Authorization": f"Bearer {registered_token}"}
