"""Manual trip-builder REST router.

Registered separately from :class:`TripsWebRouter` and gated behind the
``manual_builder_enabled`` feature flag so the surface can be removed
without touching the AI flow.
"""
from __future__ import annotations

from fastapi import FastAPI, status

from src.components.trips.web.models.TripResponse import TripResponse
from src.components.travel_plan.web.views.ManualBuilderViews import (
    AddPlaceToDayView,
    AddToWishlistView,
    AskAiForTripView,
    CreateManualTripView,
    MovePlaceView,
    OptimizeDayView,
    OptimizeDayPreviewView,
    PromoteFromWishlistView,
    RemoveFromWishlistView,
    RemovePlaceFromDayView,
    ReorderDayView,
    SearchPlacesView,
    UpdateActivityView,
    UpdateBudgetView,
    UpdateHotelView,
)


class ManualBuilderWebRouter:
    """Registers all manual trip-builder endpoints onto the FastAPI app."""

    def __call__(self, app: FastAPI, prefix: str = '') -> None:
        TAG = 'trip-builder'

        # 1. Create manual trip
        app.add_api_route(
            f'{prefix}/trips/manual',
            endpoint=CreateManualTripView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            status_code=status.HTTP_201_CREATED,
            tags=[TAG],
        )
        # 2. Add place to day
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/places',
            endpoint=AddPlaceToDayView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 3. Update activity
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/places/'
            f'{{activity_index}}',
            endpoint=UpdateActivityView().__call__,
            methods=['PATCH'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 4. Remove place from day
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/places/'
            f'{{activity_index}}',
            endpoint=RemovePlaceFromDayView().__call__,
            methods=['DELETE'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 5. Reorder day
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/reorder',
            endpoint=ReorderDayView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 6. Move place between days
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/places/move',
            endpoint=MovePlaceView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 7. Add to wishlist
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/wishlist',
            endpoint=AddToWishlistView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 8. Remove from wishlist
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/wishlist/{{wishlist_index}}',
            endpoint=RemoveFromWishlistView().__call__,
            methods=['DELETE'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 9. Promote from wishlist
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/wishlist/{{wishlist_index}}/promote',
            endpoint=PromoteFromWishlistView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 10. Update budget
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/budget',
            endpoint=UpdateBudgetView().__call__,
            methods=['PATCH'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 11. Optimize day
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/optimize',
            endpoint=OptimizeDayView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 11a. Optimize day preview (returns diff, no persist)
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/optimize/preview',
            endpoint=OptimizeDayPreviewView().__call__,
            methods=['POST'],
            tags=[TAG],
        )
        # 11b. Update hotel
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/hotel',
            endpoint=UpdateHotelView().__call__,
            methods=['PATCH'],
            response_model=TripResponse,
            tags=[TAG],
        )
        # 12. Search places (501 stub)
        app.add_api_route(
            f'{prefix}/places/search',
            endpoint=SearchPlacesView().__call__,
            methods=['POST'],
            tags=[TAG],
        )
        # 13. Ask AI about this trip
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/ask-ai',
            endpoint=AskAiForTripView().__call__,
            methods=['POST'],
            tags=[TAG],
        )
