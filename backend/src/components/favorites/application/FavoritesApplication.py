from dishka import Provider, Scope
from src.components.favorites.application.core.commands import (
    IAddToFavoritesCommand,
    IRemoveFromFavoritesCommand,
    IUpdateFavoriteCommand,
)
from src.components.favorites.application.core.queries import (
    IGetUserFavoritesQuery,
    IIsFavoritedQuery,
)
from src.components.favorites.application.impl.commands import (
    AddToFavoritesCommand,
    RemoveFromFavoritesCommand,
    UpdateFavoriteCommand,
)
from src.components.favorites.application.impl.queries import (
    GetUserFavoritesQuery,
    IsFavoritedQuery,
)

__all__ = ['FavoritesApplication']


class FavoritesApplication:
    def __call__(self) -> Provider:
        provider = Provider(scope=Scope.REQUEST)

        provider.provide(AddToFavoritesCommand, provides=IAddToFavoritesCommand)
        provider.provide(RemoveFromFavoritesCommand, provides=IRemoveFromFavoritesCommand)
        provider.provide(UpdateFavoriteCommand, provides=IUpdateFavoriteCommand)

        provider.provide(GetUserFavoritesQuery, provides=IGetUserFavoritesQuery)
        provider.provide(IsFavoritedQuery, provides=IIsFavoritedQuery)

        return provider
