from __future__ import annotations

from dishka import Provider, Scope

from src.components.trips.application.core.commands import (
    ICreateTripCommand,
    IUpdateTripCommand,
    IUpdateGeneratedPlanCommand,
    IDeleteTripCommand,
)
from src.components.trips.application.core.queries import (
    IGetTripQuery,
    IListUserTripsQuery,
)
from src.components.trips.application.impl.commands import (
    CreateTripCommand,
    UpdateTripCommand,
    UpdateGeneratedPlanCommand,
    DeleteTripCommand,
)
from src.components.trips.application.impl.queries import (
    GetTripQuery,
    ListUserTripsQuery,
)


class TripsApplication:

    def __call__(self) -> Provider:
        provider = Provider(scope=Scope.REQUEST)

        provider.provide(CreateTripCommand, provides=ICreateTripCommand)
        provider.provide(UpdateTripCommand, provides=IUpdateTripCommand)
        provider.provide(UpdateGeneratedPlanCommand, provides=IUpdateGeneratedPlanCommand)
        provider.provide(DeleteTripCommand, provides=IDeleteTripCommand)

        provider.provide(GetTripQuery, provides=IGetTripQuery)
        provider.provide(ListUserTripsQuery, provides=IListUserTripsQuery)

        return provider
