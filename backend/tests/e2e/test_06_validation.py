"""
E2E tests: Edge Cases & Validation

Tests input validation, error handling, and edge cases across all components.
"""
import httpx
import pytest

BASE_URL = "http://localhost:8081/api/v1"


class TestValidationAndEdgeCases:
    """Input validation and error handling across components."""

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, auth_headers: dict):
        self.__class__.headers = auth_headers

    # ── Auth validation ───────────────────────────────────────────

    def test_register_invalid_email(self, client: httpx.Client):
        """Registering with invalid email returns 422."""
        resp = client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "ValidPass1!",
        })
        assert resp.status_code == 422

    def test_register_short_password(self, client: httpx.Client):
        """Registering with too short password returns 422."""
        resp = client.post("/auth/register", json={
            "email": "short@test.com",
            "password": "123",
        })
        assert resp.status_code == 422

    def test_register_missing_fields(self, client: httpx.Client):
        """Registering without required fields returns 422."""
        resp = client.post("/auth/register", json={})
        assert resp.status_code == 422

    def test_login_wrong_password(self, client: httpx.Client, unique_email: str):
        """Login with wrong password returns 400."""
        resp = client.post("/auth/login", data={
            "username": unique_email,
            "password": "WrongPassword!",
        })
        assert resp.status_code == 400

    def test_login_nonexistent_user(self, client: httpx.Client):
        """Login with non-existent email returns 400."""
        resp = client.post("/auth/login", data={
            "username": "nonexistent@test.com",
            "password": "SomePass1!",
        })
        assert resp.status_code == 400

    # ── Profile validation ────────────────────────────────────────

    def test_profile_invalid_activity_level(self, client: httpx.Client):
        """Creating profile with invalid activity level returns 422."""
        resp = client.post("/users/me/profile", json={
            "activity_level": "invalid_level",
            "budget_level": "comfort",
        }, headers=self.headers)
        assert resp.status_code == 422

    def test_profile_invalid_category_value(self, client: httpx.Client):
        """Category preference value out of range returns 422."""
        resp = client.post("/users/me/profile", json={
            "activity_level": "moderate",
            "budget_level": "comfort",
            "category_preferences": {"museum": 999},
        }, headers=self.headers)
        assert resp.status_code == 422

    # ── Chat validation ───────────────────────────────────────────

    def test_update_chat_invalid_id(self, client: httpx.Client):
        """Updating a non-existent chat returns 404."""
        resp = client.patch("/chats/999999", json={
            "title": "Test",
        }, headers=self.headers)
        assert resp.status_code == 404

    # ── Trip validation ───────────────────────────────────────────

    def test_create_trip_missing_name(self, client: httpx.Client):
        """Creating a trip without a name returns 422."""
        resp = client.post("/trips/", json={
            "destination": "Somewhere",
        }, headers=self.headers)
        assert resp.status_code == 422

    def test_create_trip_invalid_dates(self, client: httpx.Client):
        """Creating a trip with invalid date format returns 422."""
        resp = client.post("/trips/", json={
            "name": "Bad Trip",
            "start_date": "not-a-date",
        }, headers=self.headers)
        assert resp.status_code == 422

    # ── Favorites validation ──────────────────────────────────────

    def test_add_favorite_missing_chat_id(self, client: httpx.Client):
        """Adding favorite without chat_id returns 422."""
        resp = client.post("/favorites", json={}, headers=self.headers)
        assert resp.status_code == 422

    # ── Health check ──────────────────────────────────────────────

    def test_health_check(self, client: httpx.Client):
        """Health endpoint returns healthy."""
        # Health endpoint is at root level, not under /api/v1
        resp = httpx.get("http://localhost:8081/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_root_endpoint(self, client: httpx.Client):
        """Root endpoint returns ok."""
        resp = httpx.get("http://localhost:8081/")
        assert resp.status_code == 200
