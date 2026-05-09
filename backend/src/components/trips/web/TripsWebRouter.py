from __future__ import annotations

from typing import List

from fastapi import FastAPI, Response, status

from src.components.trips.web.models.TripCreateRequest import TripCreateRequest
from src.components.trips.web.models.TripResponse import TripResponse
from src.components.trips.web.views.CreateTripView import CreateTripView
from src.components.trips.web.views.ListTripsView import ListTripsView
from src.components.trips.web.views.GetTripView import GetTripView
from src.components.trips.web.views.ReplanTripDayView import ReplanTripDayView
from src.components.trips.web.views.DeleteTripView import DeleteTripView


class TripsWebRouter:

    def __call__(self, app: FastAPI, prefix: str = ''):
        app.add_api_route(
            f'{prefix}/trips/',
            endpoint=CreateTripView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            status_code=status.HTTP_201_CREATED,
            tags=['trips'],
        )
        app.add_api_route(
            f'{prefix}/trips/',
            endpoint=ListTripsView().__call__,
            methods=['GET'],
            response_model=List[TripResponse],
            tags=['trips'],
        )
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}',
            endpoint=GetTripView().__call__,
            methods=['GET'],
            response_model=TripResponse,
            tags=['trips'],
        )
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}/days/{{day_number}}/replan',
            endpoint=ReplanTripDayView().__call__,
            methods=['POST'],
            response_model=TripResponse,
            tags=['trips'],
        )
        app.add_api_route(
            f'{prefix}/trips/{{trip_id}}',
            endpoint=DeleteTripView().__call__,
            methods=['DELETE'],
            status_code=status.HTTP_204_NO_CONTENT,
            response_class=Response,
            response_model=None,
            tags=['trips'],
        )
