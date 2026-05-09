"""
E2E tests: User Story — Manual Trip Builder

Verifies the full manual-builder REST surface against a live backend
on localhost:8081. Covers:

1.  Create manual trip without a hotel (server geocodes a placeholder).
2.  Create manual trip with an explicit hotel.
3.  Update hotel: set explicit → clear (back to auto placeholder).
4.  Add / reorder / move places between days.
5.  Wishlist add → promote → list.
6.  Update budget.
7.  Optimize a day (>=2 activities).
8.  Search places.
9.  Optimistic-lock 409 conflict on stale ``expected_version``.
10. Delete trip → 204 + 404 on subsequent fetch.
"""
from __future__ import annotations

import httpx
import pytest


# ── Helpers ─────────────────────────────────────────────────────────
def _plan(trip: dict) -> dict:
    """Extract the manual-builder plan_data block.

    Manual trips wrap the plan as ``generated_plan.plan_data``. We also
    fall back to the unwrapped form so the helper is robust for trips
    that have been touched by the agent (``source='mixed'``).
    """
    gp = trip.get('generated_plan') or {}
    inner = gp.get('plan_data')
    return inner if isinstance(inner, dict) else gp


def _version(trip: dict) -> int:
    return int(_plan(trip).get('version') or 1)


def _place(name: str, lat: float, lon: float, **extra) -> dict:
    base = {
        'name': name,
        'lat': lat,
        'lon': lon,
        'category': 'landmark',
        'visit_duration_min': 60,
    }
    base.update(extra)
    return base


# ── Suite ───────────────────────────────────────────────────────────
class TestManualBuilder:
    """One linear story per class — state shared via class attributes."""

    trip_no_hotel: int = 0
    trip_with_hotel: int = 0

    @pytest.fixture(autouse=True, scope='class')
    def setup(self, auth_headers: dict):
        self.__class__.headers = auth_headers

    # 1. Create without hotel — server geocodes "Центр …" placeholder
    def test_01_create_without_hotel(self, client: httpx.Client):
        resp = client.post(
            '/trips/manual',
            json={
                'name': 'Manual Omsk',
                'destination': 'Омск',
                'start_date': '2026-08-01',
                'end_date': '2026-08-03',
                'start_hour': 9,
            },
            headers=self.headers,
        )
        assert resp.status_code == 201, resp.text
        trip = resp.json()
        TestManualBuilder.trip_no_hotel = trip['id']
        plan = _plan(trip)
        # Skeleton: 3 days, empty activities, auto hotel
        assert plan['source'] == 'manual'
        assert len(plan['days']) == 3
        for day in plan['days']:
            assert day['activities'] == []
        hotel = plan['hotel']
        assert hotel is not None
        assert hotel.get('source') == 'auto'
        assert 'Центр' in hotel['name']

    # 2. Create with explicit hotel
    def test_02_create_with_hotel(self, client: httpx.Client):
        resp = client.post(
            '/trips/manual',
            json={
                'name': 'Manual Paris',
                'destination': 'Paris',
                'start_date': '2026-09-01',
                'end_date': '2026-09-02',
                'start_hour': 10,
                'hotel': _place('Hotel Lutetia', 48.8512, 2.3265, category='other'),
            },
            headers=self.headers,
        )
        assert resp.status_code == 201, resp.text
        trip = resp.json()
        TestManualBuilder.trip_with_hotel = trip['id']
        hotel = _plan(trip)['hotel']
        assert hotel['name'] == 'Hotel Lutetia'
        assert hotel.get('source') != 'auto'

    # 3. Update hotel → clear (back to auto)
    def test_03_update_hotel_clear(self, client: httpx.Client):
        # First read current version
        resp = client.get(f'/trips/{self.trip_with_hotel}', headers=self.headers)
        version = _version(resp.json())
        # Replace with a new explicit hotel
        resp = client.patch(
            f'/trips/{self.trip_with_hotel}/hotel',
            json={
                'hotel': _place('Hotel Le Bristol', 48.8717, 2.3163, category='other'),
                'expected_version': version,
            },
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        assert plan['hotel']['name'] == 'Hotel Le Bristol'
        version = plan['version']
        # Now clear → auto placeholder
        resp = client.patch(
            f'/trips/{self.trip_with_hotel}/hotel',
            json={'hotel': None, 'expected_version': version},
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        hotel = _plan(resp.json())['hotel']
        assert hotel.get('source') == 'auto'

    # 4. Add places to day 1, reorder, move to day 2
    def test_04_add_reorder_move_places(self, client: httpx.Client):
        tid = self.trip_no_hotel
        resp = client.get(f'/trips/{tid}', headers=self.headers)
        version = _version(resp.json())
        # Add three places to day 1
        for idx, p in enumerate([
            _place('Tarsky Gate', 54.9870, 73.3680),
            _place('Lubinsky Avenue', 54.9892, 73.3686),
            _place('Assumption Cathedral', 54.9898, 73.3686),
        ]):
            resp = client.post(
                f'/trips/{tid}/days/1/places',
                json={'place': p, 'expected_version': version},
                headers=self.headers,
            )
            assert resp.status_code == 200, resp.text
            version = _version(resp.json())

        resp = client.get(f'/trips/{tid}', headers=self.headers)
        plan = _plan(resp.json())
        assert len(plan['days'][0]['activities']) == 3

        # Reorder day 1: reverse
        resp = client.post(
            f'/trips/{tid}/days/1/reorder',
            json={'new_indices': [2, 1, 0], 'expected_version': version},
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        names = [a['place']['name'] for a in plan['days'][0]['activities']]
        assert names[0] == 'Assumption Cathedral'
        version = plan['version']

        # Move first activity from day 1 to day 2
        resp = client.post(
            f'/trips/{tid}/places/move',
            json={
                'from_day': 1, 'to_day': 2, 'activity_index': 0,
                'expected_version': version,
            },
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        assert len(plan['days'][0]['activities']) == 2
        assert len(plan['days'][1]['activities']) == 1

    # 5. Wishlist add → promote
    def test_05_wishlist_add_and_promote(self, client: httpx.Client):
        tid = self.trip_no_hotel
        resp = client.get(f'/trips/{tid}', headers=self.headers)
        version = _version(resp.json())
        resp = client.post(
            f'/trips/{tid}/wishlist',
            json={
                'place': _place('Omsk Drama Theatre', 54.9885, 73.3697),
                'expected_version': version,
            },
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        assert len(plan.get('wishlist') or []) == 1
        version = plan['version']
        # Promote first wishlist item to day 3
        resp = client.post(
            f'/trips/{tid}/wishlist/0/promote',
            json={'day_number': 3, 'expected_version': version},
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        assert (plan.get('wishlist') or []) == []
        assert any(
            a['place']['name'] == 'Omsk Drama Theatre'
            for a in plan['days'][2]['activities']
        )

    # 6. Update budget
    def test_06_update_budget(self, client: httpx.Client):
        tid = self.trip_no_hotel
        resp = client.get(f'/trips/{tid}', headers=self.headers)
        version = _version(resp.json())
        resp = client.patch(
            f'/trips/{tid}/budget',
            json={
                'total': 50000.0,
                'currency': 'RUB',
                'expected_version': version,
            },
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        assert plan.get('budget_total') == 50000.0
        assert plan.get('budget_currency') == 'RUB'

    # 7. Optimize day 1 (>=2 activities required)
    def test_07_optimize_day(self, client: httpx.Client):
        tid = self.trip_no_hotel
        resp = client.get(f'/trips/{tid}', headers=self.headers)
        version = _version(resp.json())
        resp = client.post(
            f'/trips/{tid}/days/1/optimize',
            json={'expected_version': version},
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        plan = _plan(resp.json())
        assert len(plan['days'][0]['activities']) >= 2

    # 8. Search places
    def test_08_search_places(self, client: httpx.Client):
        resp = client.post(
            '/places/search',
            json={
                'query': 'museum',
                'near_lat': 54.9885,
                'near_lon': 73.3697,
                'radius_km': 50.0,
                'limit': 5,
            },
            headers=self.headers,
        )
        # Some envs may have no provider configured → results may be
        # empty; upstream errors are also tolerated as a soft skip.
        assert resp.status_code in (200, 502, 503), resp.text
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict)
            assert 'results' in data
            assert isinstance(data['results'], list)

    # 9. Stale expected_version → 409
    def test_09_version_conflict(self, client: httpx.Client):
        tid = self.trip_no_hotel
        resp = client.post(
            f'/trips/{tid}/days/1/places',
            json={
                'place': _place('Stale add', 54.99, 73.37),
                'expected_version': 1,  # almost certainly stale by now
            },
            headers=self.headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        detail = body.get('detail') if isinstance(body, dict) else None
        assert isinstance(detail, dict)
        assert detail.get('error') == 'version_conflict'
        assert 'expected' in detail and 'actual' in detail

    # 10. Delete trip → 204 + 404 afterwards
    def test_10_delete_trip(self, client: httpx.Client):
        tid = self.trip_with_hotel
        resp = client.delete(f'/trips/{tid}', headers=self.headers)
        assert resp.status_code == 204
        resp = client.get(f'/trips/{tid}', headers=self.headers)
        assert resp.status_code == 404
