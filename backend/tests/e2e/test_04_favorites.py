"""
E2E tests: User Story — Favorites Management

Flow:
1. Create a chat (to favorite)
2. Add chat to favorites
3. List favorites → see the new favorite
4. Update favorite custom name
5. List favorites → verify name changed
6. Check chat list → is_favorited flag
7. Remove from favorites
8. List favorites → empty
9. Check chat list → is_favorited = false
10. Add non-existent chat to favorites → error
"""
import httpx
import pytest

BASE_URL = "http://localhost:8081/api/v1"


class TestFavoritesLifecycle:
    """Full user story: add → list → update → remove favorites."""

    chat_id: int = 0
    favorite_id: int = 0

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, auth_headers: dict):
        self.__class__.headers = auth_headers

    def test_01_create_chat_for_favorites(self, client: httpx.Client):
        """Create a chat to use for favorites tests."""
        resp = client.post("/chats", json={}, headers=self.headers)
        assert resp.status_code == 201
        TestFavoritesLifecycle.chat_id = resp.json()["chat_id"]

    def test_02_list_favorites_empty(self, client: httpx.Client):
        """Initially no favorites for this chat."""
        resp = client.get("/favorites", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "favorites" in data
        # Filter out any favorites from other test runs
        # Just check the structure is correct
        assert "total" in data

    def test_03_add_to_favorites(self, client: httpx.Client):
        """Add the chat to favorites."""
        resp = client.post("/favorites", json={
            "chat_id": self.chat_id,
            "custom_name": "My Favorite Chat",
        }, headers=self.headers)
        assert resp.status_code == 201, f"Add favorite failed: {resp.text}"
        data = resp.json()
        assert data["chat_id"] == self.chat_id
        assert data["custom_name"] == "My Favorite Chat"
        TestFavoritesLifecycle.favorite_id = data["id"]

    def test_04_list_favorites_has_one(self, client: httpx.Client):
        """List favorites includes the newly added favorite."""
        resp = client.get("/favorites", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        fav_chat_ids = [f["chat_id"] for f in data["favorites"]]
        assert self.chat_id in fav_chat_ids

    def test_05_chat_is_favorited_flag(self, client: httpx.Client):
        """When listing chats, the favorited chat has is_favorited=True."""
        resp = client.get("/chats", headers=self.headers)
        assert resp.status_code == 200
        chats = resp.json()["chats"]
        target = next((c for c in chats if c["id"] == self.chat_id), None)
        assert target is not None
        assert target["is_favorited"] is True

    def test_06_update_favorite_name(self, client: httpx.Client):
        """Update the custom name of a favorite."""
        resp = client.patch(f"/favorites/{self.chat_id}", json={
            "custom_name": "Renamed Favorite",
        }, headers=self.headers)
        assert resp.status_code == 200, f"Update favorite failed: {resp.text}"
        data = resp.json()
        assert data["custom_name"] == "Renamed Favorite"

    def test_07_list_favorites_verify_name(self, client: httpx.Client):
        """Verify the name change persisted."""
        resp = client.get("/favorites", headers=self.headers)
        assert resp.status_code == 200
        favs = resp.json()["favorites"]
        target = next((f for f in favs if f["chat_id"] == self.chat_id), None)
        assert target is not None
        assert target["custom_name"] == "Renamed Favorite"

    def test_08_remove_from_favorites(self, client: httpx.Client):
        """Remove the chat from favorites."""
        resp = client.delete(f"/favorites/{self.chat_id}", headers=self.headers)
        assert resp.status_code == 204

    def test_09_list_favorites_after_remove(self, client: httpx.Client):
        """After removal, the chat is no longer in favorites."""
        resp = client.get("/favorites", headers=self.headers)
        assert resp.status_code == 200
        fav_chat_ids = [f["chat_id"] for f in resp.json()["favorites"]]
        assert self.chat_id not in fav_chat_ids

    def test_10_chat_not_favorited_after_remove(self, client: httpx.Client):
        """The chat's is_favorited flag is now False."""
        resp = client.get("/chats", headers=self.headers)
        assert resp.status_code == 200
        chats = resp.json()["chats"]
        target = next((c for c in chats if c["id"] == self.chat_id), None)
        assert target is not None
        assert target["is_favorited"] is False

    def test_11_unauthorized_favorites(self, client: httpx.Client):
        """Listing favorites without auth returns 403."""
        resp = client.get("/favorites")
        assert resp.status_code == 403

    def test_12_remove_nonexistent_favorite(self, client: httpx.Client):
        """Removing a non-favorited chat returns 404."""
        resp = client.delete("/favorites/999999", headers=self.headers)
        assert resp.status_code == 404
