"""
E2E tests: User Story — Authentication & Profile Management

Flow:
1. Register new user → get token
2. Login with same credentials → get token
3. Duplicate registration → 400
4. Check profile status → no profile
5. Create profile → 201
6. Read profile → verify fields
7. Update profile → verify changes
8. Duplicate create profile → 400
"""
import httpx
import pytest

BASE_URL = "http://localhost:8081/api/v1"


class TestAuthAndProfile:
    """Full user story: registration → login → profile CRUD."""

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, registered_token: str, unique_email: str, user_password: str, auth_headers: dict):
        self.__class__.token = registered_token
        self.__class__.email = unique_email
        self.__class__.password = user_password
        self.__class__.headers = auth_headers

    def test_01_register_returns_token(self, client: httpx.Client):
        """Registration already done in fixture; verify token works."""
        resp = client.get("/users/me/profile/status", headers=self.headers)
        assert resp.status_code == 200

    def test_02_login_with_credentials(self, client: httpx.Client):
        """Login with registered credentials returns a valid token."""
        resp = client.post("/auth/login", data={
            "username": self.email,
            "password": self.password,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_03_register_duplicate_email(self, client: httpx.Client):
        """Registering the same email again returns 400."""
        resp = client.post("/auth/register", json={
            "email": self.email,
            "password": self.password,
        })
        assert resp.status_code == 400

    def test_04_profile_status_no_profile(self, client: httpx.Client):
        """Before creating a profile, status shows has_profile=False."""
        resp = client.get("/users/me/profile/status", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["has_profile"] is False

    def test_05_create_profile(self, client: httpx.Client):
        """Create a user profile with travel preferences."""
        profile_data = {
            "activity_level": "moderate",
            "budget_level": "comfort",
            "category_preferences": {
                "museum": 8, "landmark": 7, "park": 6, "restaurant": 9,
                "cafe": 5, "religious": 3, "entertainment": 7, "shopping": 4,
                "nightlife": 2, "nature": 8, "viewpoint": 9, "beach": 6,
            },
            "landscape_preferences": {
                "sea": 8, "mountains": 7, "city": 6,
                "village": 4, "forest": 5, "desert": 2,
            },
            "food_preferences": {"vegetarian": False, "halal": False, "local_cuisine": True},
            "start_hour": 9,
            "meal_count_per_day": 2,
        }
        resp = client.post("/users/me/profile", json=profile_data, headers=self.headers)
        assert resp.status_code == 201, f"Create profile failed: {resp.text}"
        data = resp.json()
        assert data["activity_level"] == "moderate"
        assert data["budget_level"] == "comfort"
        assert data["start_hour"] == 9
        assert data["meal_count_per_day"] == 2
        assert data["category_preferences"]["museum"] == 8

    def test_06_profile_status_has_profile(self, client: httpx.Client):
        """After creating profile, status shows has_profile=True."""
        resp = client.get("/users/me/profile/status", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["has_profile"] is True

    def test_07_read_profile(self, client: httpx.Client):
        """Read the created profile and verify all fields."""
        resp = client.get("/users/me/profile", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["activity_level"] == "moderate"
        assert data["budget_level"] == "comfort"
        assert data["landscape_preferences"]["sea"] == 8
        assert data["food_preferences"]["local_cuisine"] is True

    def test_08_update_profile(self, client: httpx.Client):
        """Update profile fields and verify changes."""
        update_data = {
            "activity_level": "active",
            "budget_level": "economy",
            "category_preferences": {
                "museum": 10, "landmark": 10, "park": 5, "restaurant": 5,
                "cafe": 5, "religious": 5, "entertainment": 5, "shopping": 5,
                "nightlife": 5, "nature": 5, "viewpoint": 5, "beach": 5,
            },
            "landscape_preferences": {
                "sea": 3, "mountains": 10, "city": 5,
                "village": 5, "forest": 5, "desert": 5,
            },
            "food_preferences": {"vegetarian": True, "halal": False},
            "start_hour": 11,
            "meal_count_per_day": 3,
        }
        resp = client.put("/users/me/profile", json=update_data, headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["activity_level"] == "active"
        assert data["budget_level"] == "economy"
        assert data["start_hour"] == 11
        assert data["meal_count_per_day"] == 3

    def test_09_create_profile_duplicate(self, client: httpx.Client):
        """Creating a profile again returns 400."""
        resp = client.post("/users/me/profile", json={
            "activity_level": "calm",
            "budget_level": "unlimited",
        }, headers=self.headers)
        assert resp.status_code == 400

    def test_10_unauthorized_access(self, client: httpx.Client):
        """Accessing protected endpoints without token returns 403."""
        resp = client.get("/users/me/profile")
        assert resp.status_code == 403

    def test_11_invalid_token(self, client: httpx.Client):
        """Accessing with an invalid token returns 401."""
        resp = client.get("/users/me/profile", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401
