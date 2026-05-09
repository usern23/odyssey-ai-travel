"""
E2E tests: User Story — Chat Lifecycle

Flow:
1. Create chat (empty, no agent message)
2. List chats → see the new chat
3. Get chat by ID → verify details
4. Update chat title
5. Get chat by ID → verify title changed
6. Create second chat
7. List chats → total = 2
8. Delete first chat
9. List chats → total = 1
10. Get deleted chat → 404
"""
import httpx
import pytest

BASE_URL = "http://localhost:8081/api/v1"


class TestChatLifecycle:
    """Full user story: create → list → read → update → delete chats."""

    chat_id_1: int = 0
    chat_id_2: int = 0

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, auth_headers: dict):
        self.__class__.headers = auth_headers

    def test_01_create_chat_empty(self, client: httpx.Client):
        """Create a chat without a message (no agent interaction)."""
        resp = client.post("/chats", json={}, headers=self.headers)
        assert resp.status_code == 201, f"Create chat failed: {resp.text}"
        data = resp.json()
        assert "chat_id" in data
        assert "reply" in data
        TestChatLifecycle.chat_id_1 = data["chat_id"]

    def test_02_list_chats_has_one(self, client: httpx.Client):
        """List chats returns at least the created chat."""
        resp = client.get("/chats", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "chats" in data
        assert data["total"] >= 1
        chat_ids = [c["id"] for c in data["chats"]]
        assert self.chat_id_1 in chat_ids

    def test_03_get_chat_by_id(self, client: httpx.Client):
        """Get a specific chat with messages."""
        resp = client.get(f"/chats/{self.chat_id_1}", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == self.chat_id_1
        assert "messages" in data

    def test_04_update_chat_title(self, client: httpx.Client):
        """Update the title of the chat."""
        resp = client.patch(
            f"/chats/{self.chat_id_1}",
            json={"title": "Updated Test Title"},
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated Test Title"

    def test_05_get_chat_verify_title(self, client: httpx.Client):
        """Verify the title was persisted."""
        resp = client.get(f"/chats/{self.chat_id_1}", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Test Title"

    def test_06_create_second_chat(self, client: httpx.Client):
        """Create a second chat."""
        resp = client.post("/chats", json={}, headers=self.headers)
        assert resp.status_code == 201
        TestChatLifecycle.chat_id_2 = resp.json()["chat_id"]
        assert self.chat_id_2 != self.chat_id_1

    def test_07_list_chats_has_two(self, client: httpx.Client):
        """List chats returns both chats."""
        resp = client.get("/chats", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        chat_ids = [c["id"] for c in data["chats"]]
        assert self.chat_id_1 in chat_ids
        assert self.chat_id_2 in chat_ids

    def test_08_delete_chat(self, client: httpx.Client):
        """Delete the first chat."""
        resp = client.delete(f"/chats/{self.chat_id_1}", headers=self.headers)
        assert resp.status_code == 204

    def test_09_list_chats_after_delete(self, client: httpx.Client):
        """First chat is gone, second remains."""
        resp = client.get("/chats", headers=self.headers)
        assert resp.status_code == 200
        chat_ids = [c["id"] for c in resp.json()["chats"]]
        assert self.chat_id_1 not in chat_ids
        assert self.chat_id_2 in chat_ids

    def test_10_get_deleted_chat_404(self, client: httpx.Client):
        """Getting the deleted chat returns 404."""
        resp = client.get(f"/chats/{self.chat_id_1}", headers=self.headers)
        assert resp.status_code == 404

    def test_11_get_nonexistent_chat_404(self, client: httpx.Client):
        """Getting a chat that never existed returns 404."""
        resp = client.get("/chats/999999", headers=self.headers)
        assert resp.status_code == 404

    def test_12_delete_nonexistent_chat_404(self, client: httpx.Client):
        """Deleting a nonexistent chat returns 404."""
        resp = client.delete("/chats/999999", headers=self.headers)
        assert resp.status_code == 404

    def test_13_unauthorized_list_chats(self, client: httpx.Client):
        """Listing chats without auth returns 403."""
        resp = client.get("/chats")
        assert resp.status_code == 403
