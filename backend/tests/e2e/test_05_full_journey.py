"""
E2E tests: User Story — Full Cross-Component User Journey

Simulates a complete new user journey:
1. Register a new user
2. Login
3. Create profile
4. Create a chat
5. Create a trip
6. Add chat to favorites
7. List everything — verify cross-component data consistency
8. Update items across components
9. Cleanup — remove favorite, delete chat
10. Verify cleanup
"""
import uuid
import httpx
import pytest

BASE_URL = "http://localhost:8081/api/v1"


class TestFullUserJourney:
    """
    Cross-component integration: auth → profile → chat → trip → favorites.
    Uses a unique user to avoid conflicts with other test classes.
    """

    token: str = ""
    headers: dict = {}
    email: str = ""
    chat_id: int = 0
    trip_id: int = 0

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        self.__class__.email = f"journey_{uuid.uuid4().hex[:8]}@test.com"

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=BASE_URL, timeout=30.0)

    def test_01_register(self):
        """Register a brand-new user."""
        with self._client() as c:
            resp = c.post("/auth/register", json={
                "email": self.email,
                "password": "JourneyPass1!",
            })
            assert resp.status_code == 201
            data = resp.json()
            TestFullUserJourney.token = data["access_token"]
            TestFullUserJourney.headers = {"Authorization": f"Bearer {self.token}"}

    def test_02_login(self):
        """Login with the same credentials."""
        with self._client() as c:
            resp = c.post("/auth/login", data={
                "username": self.email,
                "password": "JourneyPass1!",
            })
            assert resp.status_code == 200
            assert "access_token" in resp.json()

    def test_03_create_profile(self):
        """Create travel profile."""
        with self._client() as c:
            resp = c.post("/users/me/profile", json={
                "activity_level": "active",
                "budget_level": "unlimited",
                "start_hour": 10,
                "meal_count_per_day": 2,
            }, headers=self.headers)
            assert resp.status_code == 201
            data = resp.json()
            assert data["activity_level"] == "active"

    def test_04_read_profile(self):
        """Read back the profile."""
        with self._client() as c:
            resp = c.get("/users/me/profile", headers=self.headers)
            assert resp.status_code == 200
            assert resp.json()["budget_level"] == "unlimited"

    def test_05_create_chat(self):
        """Create a chat (empty, no agent)."""
        with self._client() as c:
            resp = c.post("/chats", json={}, headers=self.headers)
            assert resp.status_code == 201
            TestFullUserJourney.chat_id = resp.json()["chat_id"]

    def test_06_create_trip(self):
        """Create a trip."""
        with self._client() as c:
            resp = c.post("/trips/", json={
                "name": "Journey Trip",
                "destination": "Paris",
                "start_date": "2025-09-01",
                "end_date": "2025-09-10",
            }, headers=self.headers)
            assert resp.status_code == 201
            TestFullUserJourney.trip_id = resp.json()["id"]

    def test_07_add_favorite(self):
        """Add the chat to favorites."""
        with self._client() as c:
            resp = c.post("/favorites", json={
                "chat_id": self.chat_id,
                "custom_name": "Journey Chat",
            }, headers=self.headers)
            assert resp.status_code == 201

    def test_08_verify_all_lists(self):
        """Verify all components return consistent data."""
        with self._client() as c:
            # Chats
            chats_resp = c.get("/chats", headers=self.headers)
            assert chats_resp.status_code == 200
            chats = chats_resp.json()
            chat_ids = [ch["id"] for ch in chats["chats"]]
            assert self.chat_id in chat_ids

            # Chat is favorited
            target_chat = next(ch for ch in chats["chats"] if ch["id"] == self.chat_id)
            assert target_chat["is_favorited"] is True

            # Trips
            trips_resp = c.get("/trips/", headers=self.headers)
            assert trips_resp.status_code == 200
            trip_ids = [t["id"] for t in trips_resp.json()]
            assert self.trip_id in trip_ids

            # Favorites
            favs_resp = c.get("/favorites", headers=self.headers)
            assert favs_resp.status_code == 200
            fav_chat_ids = [f["chat_id"] for f in favs_resp.json()["favorites"]]
            assert self.chat_id in fav_chat_ids

    def test_09_update_chat_title(self):
        """Update chat title."""
        with self._client() as c:
            resp = c.patch(f"/chats/{self.chat_id}", json={
                "title": "Journey Updated Title",
            }, headers=self.headers)
            assert resp.status_code == 200
            assert resp.json()["title"] == "Journey Updated Title"

    def test_10_cleanup_remove_favorite(self):
        """Remove chat from favorites."""
        with self._client() as c:
            resp = c.delete(f"/favorites/{self.chat_id}", headers=self.headers)
            assert resp.status_code == 204

    def test_11_cleanup_delete_chat(self):
        """Delete the chat."""
        with self._client() as c:
            resp = c.delete(f"/chats/{self.chat_id}", headers=self.headers)
            assert resp.status_code == 204

    def test_12_verify_cleanup(self):
        """Verify chat is gone and favorites are empty."""
        with self._client() as c:
            # Chat deleted
            resp = c.get(f"/chats/{self.chat_id}", headers=self.headers)
            assert resp.status_code == 404

            # Favorites empty for this chat
            favs = c.get("/favorites", headers=self.headers)
            fav_chat_ids = [f["chat_id"] for f in favs.json()["favorites"]]
            assert self.chat_id not in fav_chat_ids
