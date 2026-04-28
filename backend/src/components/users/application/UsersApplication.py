from dishka import Provider, Scope
from src.components.users.application.core.commands import (
    IRegisterUserCommand, IGetOrCreateYandexUserCommand,
    ICreateProfileCommand, IUpdateProfileCommand,
)
from src.components.users.application.core.queries import (
    IAuthenticateUserQuery, IGetProfileQuery,
)
from src.components.users.application.impl.commands import (
    RegisterUserCommand, GetOrCreateYandexUserCommand,
    CreateProfileCommand, UpdateProfileCommand,
)
from src.components.users.application.impl.queries import (
    AuthenticateUserQuery, GetProfileQuery,
)

__all__ = ['UsersApplication']


class UsersApplication:
    def __call__(self) -> Provider:
        provider = Provider(scope=Scope.REQUEST)

        provider.provide(RegisterUserCommand, provides=IRegisterUserCommand)
        provider.provide(GetOrCreateYandexUserCommand, provides=IGetOrCreateYandexUserCommand)
        provider.provide(CreateProfileCommand, provides=ICreateProfileCommand)
        provider.provide(UpdateProfileCommand, provides=IUpdateProfileCommand)

        provider.provide(AuthenticateUserQuery, provides=IAuthenticateUserQuery)
        provider.provide(GetProfileQuery, provides=IGetProfileQuery)

        return provider
