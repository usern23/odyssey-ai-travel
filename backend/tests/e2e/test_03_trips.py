"""
E2E tests: User Story — Trips CRUD

Flow:
1. Create a trip
2. List trips → see the new trip
3. Get trip by ID → verify fields
4. Create a second trip with dates
5. List trips → total = 2
6. Get nonexistent trip → 404
"""
import httpx
import pytest

BASE_URL = "http://localhost:8081/api/v1"


class TestTripsLifecycle:
    """Full user story: create → list → read trips."""

    trip_id_1: int = 0
    trip_id_2: int = 0

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, auth_headers: dict):
        self.__class__.headers = auth_headers

    def test_01_create_trip(self, client: httpx.Client):
        """Create a basic trip."""
        resp = client.post("/trips/", json={
            "name": "E2E Test Trip",
            "destination": "Tokyo",
            "origin": "Moscow",
            "trip_profile": {"style": "adventure"},
        }, headers=self.headers)
        assert resp.status_code == 201, f"Create trip failed: {resp.text}"
        data = resp.json()
        assert data["name"] == "E2E Test Trip"
        assert data["destination"] == "Tokyo"
        assert data["origin"] == "Moscow"
        assert "id" in data
        TestTripsLifecycle.trip_id_1 = data["id"]

    def test_02_list_trips(self, client: httpx.Client):
        """List trips returns at least the one we created."""
        resp = client.get("/trips/", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        trip_ids = [t["id"] for t in data]
        assert self.trip_id_1 in trip_ids

    def test_03_get_trip_by_id(self, client: httpx.Client):
        """Get a specific trip by ID."""
        resp = client.get(f"/trips/{self.trip_id_1}", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == self.trip_id_1
        assert data["name"] == "E2E Test Trip"
        assert data["destination"] == "Tokyo"

    def test_04_create_trip_with_dates(self, client: httpx.Client):
        """Create a trip with start and end dates."""
        resp = client.post("/trips/", json={
            "name": "Summer Vacation",
            "destination": "Barcelona",
            "start_date": "2025-07-01",
            "end_date": "2025-07-14",
            "trip_profile": {},
        }, headers=self.headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Summer Vacation"
        assert data["start_date"] == "2025-07-01"
        assert data["end_date"] == "2025-07-14"
        TestTripsLifecycle.trip_id_2 = data["id"]

    def test_05_list_trips_multiple(self, client: httpx.Client):
        """List trips returns both trips."""
        resp = client.get("/trips/", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        trip_ids = [t["id"] for t in data]
        assert self.trip_id_1 in trip_ids
        assert self.trip_id_2 in trip_ids

    def test_06_get_nonexistent_trip_404(self, client: httpx.Client):
        """Getting a nonexistent trip returns 404."""
        resp = client.get("/trips/999999", headers=self.headers)
        assert resp.status_code == 404

    def test_07_unauthorized_list_trips(self, client: httpx.Client):
        """Listing trips without auth returns 403."""
        resp = client.get("/trips/")
        assert resp.status_code == 403

    def test_08_create_trip_minimal(self, client: httpx.Client):
        """Create a trip with minimal fields (only name required)."""
        resp = client.post("/trips/", json={
            "name": "Quick Trip",
        }, headers=self.headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Quick Trip"
        assert data["destination"] is None
