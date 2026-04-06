from __future__ import annotations
import secrets
import warnings
from functools import lru_cache
from typing import Any, List, Optional
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore')
    app_name: str = 'Odyssey AI Backend'
    api_v1_prefix: str = '/api/v1'
    secret_key: str = 'CHANGE_ME'
    access_token_expire_minutes: int = 60
    jwt_algorithm: str = 'HS256'
    database_url: str = 'postgresql+asyncpg://postgres:postgres@localhost:5433/odyssey'
    cors_origins: Any = ['http://localhost', 'http://localhost:3000', 'http://localhost:5173']

    @field_validator('secret_key', mode='after')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == 'CHANGE_ME':
            warnings.warn(
                'SECRET_KEY is not set! Using auto-generated key. '
                'JWT tokens will be invalidated on restart. '
                'Set SECRET_KEY in .env for production.',
                stacklevel=2)
            return secrets.token_urlsafe(32)
        return v
    llm_api_base_url: Optional[str] = 'https://api.aitunnel.ru/v1/'
    llm_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            'LLM_API_KEY',
            'GEMINI_API_KEY',
            'AITUNNEL_API_KEY'))
    llm_model: Optional[str] = Field(
        default='gpt-4.1',
        validation_alias=AliasChoices(
            'LLM_MODEL',
            'GEMINI_MODEL'))
    travelpayouts_token: Optional[str] = Field(
        default=None, validation_alias=AliasChoices(
            'TRAVELPAYOUTS_TOKEN', 'TRAVEL_PAYOUTS_TOKEN'))
    geo_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            'GEO_API_KEY',
            'GEOCODER_API_KEY',
            'TWOGIS_API_KEY'))
    geocoder_base_url: str = 'https://catalog.api.2gis.com/3.0/items'
    routing_base_url: str = 'https://routing.api.2gis.com/routing/7.0.0/global'
    amadeus_api_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices(
            'AMADEUS_API_KEY', 'AMADEUS_KEY'))
    amadeus_api_secret: Optional[str] = Field(
        default=None, validation_alias=AliasChoices(
            'AMADEUS_API_SECRET', 'AMADEUS_SECRET'))
    amadeus_base_url: str = 'https://test.api.amadeus.com'
    ors_api_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices(
            'ORS_API_KEY', 'OPENROUTESERVICE_API_KEY'))
    ors_base_url: str = 'https://api.openrouteservice.org'
    rabbitmq_url: str = 'amqp://guest:guest@localhost:5672/'
    yandex_client_id: Optional[str] = None
    yandex_client_secret: Optional[str] = None

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, value: List[str] | str) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(',')]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
