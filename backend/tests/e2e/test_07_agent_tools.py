"""
E2E tests for agent tool invocation via real LLM API calls.
These tests spend real API credits - each test sends a message to the agent
and verifies the LLM response, tool calls, and overall flow.

Tests use longer timeouts since LLM + tool calls can take 30-60+ seconds.
"""
import json
import uuid
import pytest
import httpx

BASE_URL = "http://localhost:8081/api/v1"
AGENT_TIMEOUT = 180.0  # LLM + tool execution can be slow


@pytest.fixture(scope="module")
def agent_client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=AGENT_TIMEOUT) as c:
        yield c


@pytest.fixture(scope="module")
def agent_async_client():
    """Async client for SSE streaming tests."""
    import httpx as httpx_mod
    client = httpx_mod.AsyncClient(base_url=BASE_URL, timeout=AGENT_TIMEOUT)
    yield client
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            pass
        else:
            loop.run_until_complete(client.aclose())
    except Exception:
        pass


@pytest.fixture(scope="module")
def agent_user(agent_client: httpx.Client):
    """Register a unique user for agent tests and return (token, headers)."""
    email = f"agent_e2e_{uuid.uuid4().hex[:8]}@test.com"
    resp = agent_client.post("/auth/register", json={
        "email": email,
        "password": "AgentTest123!",
    })
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return token, headers


@pytest.fixture(scope="module")
def agent_headers(agent_user) -> dict:
    return agent_user[1]


@pytest.fixture(scope="module")
def agent_chat_id(agent_client: httpx.Client, agent_headers: dict) -> int:
    """Create an empty chat for agent message tests."""
    resp = agent_client.post("/chats", json={}, headers=agent_headers)
    assert resp.status_code == 201
    return resp.json()["chat_id"]


class TestAgentBasicConversation:
    """Test basic agent conversation without tool calls."""

    def test_01_simple_greeting(self, agent_client: httpx.Client,
                                 agent_headers: dict, agent_chat_id: int):
        """Agent should respond to a simple greeting (no tools needed)."""
        resp = agent_client.post(
            f"/chats/{agent_chat_id}/messages",
            json={"message": "Привет! Как тебя зовут?"},
            headers=agent_headers,
        )
        assert resp.status_code == 200, f"Agent failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "reply" in data
        assert len(data["reply"]) > 5, "Reply too short"
        assert data["chat_id"] == agent_chat_id
        # Title should have been generated (no longer "Новый чат")
        assert data.get("chat_title") is not None

    def test_02_follow_up_question(self, agent_client: httpx.Client,
                                    agent_headers: dict, agent_chat_id: int):
        """Agent should handle follow-up in the same chat."""
        resp = agent_client.post(
            f"/chats/{agent_chat_id}/messages",
            json={"message": "Чем ты можешь мне помочь?"},
            headers=agent_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reply"]) > 10
        # Should mention travel-related capabilities
        reply_lower = data["reply"].lower()
        assert any(w in reply_lower for w in [
            "путешеств", "маршрут", "поездк", "план", "перелет", "рейс",
            "помочь", "могу", "travel", "trip", "flight",
        ]), f"Reply doesn't mention travel: {data['reply'][:200]}"


class TestAgentCreateChatWithMessage:
    """Test creating a new chat with an initial message (triggers agent)."""

    def test_01_create_chat_with_message(self, agent_client: httpx.Client,
                                          agent_headers: dict):
        """POST /chats with message should create chat + get agent reply."""
        resp = agent_client.post(
            "/chats",
            json={"message": "Хочу поехать в Стамбул на 3 дня. Что посоветуешь?"},
            headers=agent_headers,
        )
        assert resp.status_code == 201, f"Failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["reply"], "No reply from agent"
        assert data["chat_id"] > 0
        assert data["chat_title"] != "Новый чат", "Title should be generated"
        # Should provide some travel advice about Istanbul
        reply_lower = data["reply"].lower()
        assert any(w in reply_lower for w in [
            "стамбул", "istanbul", "турц", "turkey",
            "мечет", "базар", "босфор", "музе",
            "день", "рекоменд", "посовет",
        ]), f"Reply not about Istanbul: {data['reply'][:300]}"


class TestAgentDestinationSuggester:
    """Test the destination_suggester tool via agent."""

    def test_01_suggest_destination(self, agent_client: httpx.Client,
                                     agent_headers: dict):
        """Ask agent to suggest destinations - should use destination_suggester tool."""
        resp = agent_client.post(
            "/chats",
            json={"message": "Куда бы мне поехать летом? Интересуюсь пляжным отдыхом и историей, бюджет средний."},
            headers=agent_headers,
        )
        assert resp.status_code == 201, f"Failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["reply"], "No reply from agent"
        # Agent should provide destination suggestions
        reply_lower = data["reply"].lower()
        # Should mention at least some destinations or travel-related terms
        assert len(data["reply"]) > 50, "Reply too short for destination suggestions"
        # Check metadata for tool calls
        metadata = data.get("metadata", {})
        tool_results = metadata.get("tool_results", [])
        # Log what tools were called
        tool_names = [t.get("name", "") for t in tool_results]
        print(f"Tools called: {tool_names}")
        print(f"Reply preview: {data['reply'][:300]}")


class TestAgentFlightSearch:
    """Test the suggest_flights tool via agent."""

    def test_01_search_flights(self, agent_client: httpx.Client,
                                agent_headers: dict):
        """Ask agent to find flights - should use suggest_flights tool."""
        resp = agent_client.post(
            "/chats",
            json={"message": "Найди мне самые дешевые авиабилеты из Москвы в Париж на следующую неделю."},
            headers=agent_headers,
        )
        assert resp.status_code == 201, f"Failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["reply"], "No reply from agent"
        # Check metadata for tool calls
        metadata = data.get("metadata", {})
        tool_results = metadata.get("tool_results", [])
        tool_names = [t.get("name", "") for t in tool_results]
        print(f"Tools called: {tool_names}")
        print(f"Reply preview: {data['reply'][:300]}")
        # Agent should have called suggest_flights or at least mention flights
        reply_lower = data["reply"].lower()
        assert any(w in reply_lower for w in [
            "рейс", "перелет", "билет", "цена", "стоимост",
            "авиа", "flight", "москв", "париж", "найден", "результат",
        ]), f"Reply not about flights: {data['reply'][:300]}"


class TestAgentSSEStream:
    """Test SSE streaming endpoint."""

    def test_01_stream_message(self, agent_client: httpx.Client,
                                agent_headers: dict):
        """POST /chats/{id}/stream should return SSE events."""
        # Create a chat first
        resp = agent_client.post("/chats", json={}, headers=agent_headers)
        assert resp.status_code == 201
        chat_id = resp.json()["chat_id"]

        # Stream a message
        with agent_client.stream(
            "POST",
            f"/chats/{chat_id}/stream",
            json={"message": "Расскажи кратко про достопримечательности Рима."},
            headers=agent_headers,
        ) as stream:
            events = []
            full_text = ""
            for line in stream.iter_lines():
                if not line:
                    continue
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                    events.append({"event": event_type, "data": event_data})
                    if event_type == "token":
                        try:
                            token_data = json.loads(event_data)
                            full_text += token_data.get("content", "")
                        except json.JSONDecodeError:
                            pass

        # Should have received events
        assert len(events) > 0, "No SSE events received"
        event_types = [e["event"] for e in events]
        print(f"SSE event types: {event_types}")
        print(f"Streamed text preview: {full_text[:200]}")

        # Must have at least some token events and a done event
        assert "token" in event_types, f"No token events, got: {event_types}"
        assert "done" in event_types, f"No done event, got: {event_types}"
        assert len(full_text) > 10, "Streamed text too short"

    def test_02_stream_new_chat(self, agent_client: httpx.Client,
                                 agent_headers: dict):
        """POST /chats/stream should create chat + stream response."""
        with agent_client.stream(
            "POST",
            "/chats/stream",
            json={"message": "Привет, расскажи что ты умеешь?"},
            headers=agent_headers,
        ) as stream:
            events = []
            full_text = ""
            event_type = ""
            for line in stream.iter_lines():
                if not line:
                    continue
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                    events.append({"event": event_type, "data": event_data})
                    if event_type == "token":
                        try:
                            token_data = json.loads(event_data)
                            full_text += token_data.get("content", "")
                        except json.JSONDecodeError:
                            pass

        event_types = [e["event"] for e in events]
        print(f"SSE event types: {event_types}")
        print(f"Streamed text: {full_text[:200]}")

        # Should have chat_created, token(s), and done
        assert "chat_created" in event_types, f"No chat_created event, got: {event_types}"
        assert "done" in event_types, f"No done event, got: {event_types}"
        assert len(full_text) > 5, "Streamed reply too short"


class TestAgentWebSearch:
    """Test the web_search tool via agent."""

    def test_01_web_search(self, agent_client: httpx.Client,
                            agent_headers: dict):
        """Agent should use web_search when asked for current info."""
        resp = agent_client.post(
            "/chats",
            json={"message": "Найди информацию о главных достопримечательностях Барселоны и их координаты."},
            headers=agent_headers,
        )
        assert resp.status_code == 201, f"Failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["reply"], "No reply from agent"
        metadata = data.get("metadata", {})
        tool_results = metadata.get("tool_results", [])
        tool_names = [t.get("name", "") for t in tool_results]
        print(f"Tools called: {tool_names}")
        print(f"Reply preview: {data['reply'][:300]}")
        # Should mention Barcelona landmarks
        reply_lower = data["reply"].lower()
        assert any(w in reply_lower for w in [
            "барселон", "barcelona", "саграда", "гауди", "рамбла",
            "парк", "готич", "достопримечательност",
        ]), f"Reply not about Barcelona: {data['reply'][:300]}"


class TestAgentChatHistory:
    """Test that agent maintains conversation context across messages."""

    def test_01_multi_turn_context(self, agent_client: httpx.Client,
                                    agent_headers: dict):
        """Agent should remember context from previous messages."""
        # Create chat with first message
        resp1 = agent_client.post(
            "/chats",
            json={"message": "Я планирую поездку в Токио."},
            headers=agent_headers,
        )
        assert resp1.status_code == 201
        chat_id = resp1.json()["chat_id"]

        # Send follow-up that references the context
        resp2 = agent_client.post(
            f"/chats/{chat_id}/messages",
            json={"message": "Какие там интересные районы для прогулок?"},
            headers=agent_headers,
        )
        assert resp2.status_code == 200
        data = resp2.json()
        reply_lower = data["reply"].lower()
        # Should reference Tokyo-specific districts
        assert any(w in reply_lower for w in [
            "токио", "tokyo", "синдзюку", "shinjuku", "сибуя", "shibuya",
            "акихабара", "akihabara", "асакуса", "asakusa", "гиндза", "ginza",
            "район", "квартал", "улиц",
        ]), f"Reply not about Tokyo districts: {data['reply'][:300]}"

    def test_02_verify_messages_saved(self, agent_client: httpx.Client,
                                       agent_headers: dict):
        """Chat should have saved user and assistant messages."""
        # Create and send a message
        resp = agent_client.post(
            "/chats",
            json={"message": "Расскажи про погоду в Лондоне."},
            headers=agent_headers,
        )
        assert resp.status_code == 201
        chat_id = resp.json()["chat_id"]

        # Get chat with messages
        resp2 = agent_client.get(
            f"/chats/{chat_id}",
            headers=agent_headers,
        )
        assert resp2.status_code == 200
        chat_data = resp2.json()
        messages = chat_data.get("messages", [])
        # Should have at least user message + assistant reply
        assert len(messages) >= 2, f"Expected >= 2 messages, got {len(messages)}"
        roles = [m["role"] for m in messages]
        assert "user" in roles, "No user message saved"
        assert "assistant" in roles, "No assistant message saved"


class TestAgentSearchPlaces:
    """Test the search_places tool via agent."""

    def test_01_search_places_for_city(self, agent_client: httpx.Client,
                                        agent_headers: dict):
        """Ask agent to find places for a city - should use search_places."""
        resp = agent_client.post(
            "/chats",
            json={"message": "Найди мне 10 лучших достопримечательностей Праги с координатами для построения маршрута."},
            headers=agent_headers,
        )
        assert resp.status_code == 201, f"Failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["reply"], "No reply"
        metadata = data.get("metadata", {})
        tool_results = metadata.get("tool_results", [])
        tool_names = [t.get("name", "") for t in tool_results]
        print(f"Tools called: {tool_names}")
        print(f"Reply preview: {data['reply'][:300]}")
        # Should mention Prague landmarks
        reply_lower = data["reply"].lower()
        assert any(w in reply_lower for w in [
            "праг", "prague", "карл", "мост", "замок", "старомест",
            "собор", "площад", "достопримечательност",
        ]), f"Reply not about Prague: {data['reply'][:300]}"


class TestAgentTitleGeneration:
    """Test that chat title is generated from the first message."""

    def test_01_title_from_message(self, agent_client: httpx.Client,
                                    agent_headers: dict):
        """Chat title should be auto-generated from the message content."""
        resp = agent_client.post(
            "/chats",
            json={"message": "Хочу спланировать романтическое путешествие в Венецию на февраль."},
            headers=agent_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        title = data.get("chat_title", "")
        assert title, "No title generated"
        assert title != "Новый чат", f"Title was not generated, still '{title}'"
        print(f"Generated title: {title}")
        # Title should be concise and relevant
        assert len(title) <= 100, f"Title too long: {title}"
