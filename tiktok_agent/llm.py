"""Cliente LLM único: Azure OpenAI (recomendado) u OpenAI directo."""
from __future__ import annotations

from functools import lru_cache

from openai import AzureOpenAI, OpenAI

from .config import settings


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    if settings.azure_endpoint and settings.azure_api_key:
        return AzureOpenAI(
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.azure_api_key,
            api_version=settings.azure_api_version,
        )
    if settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key)
    raise RuntimeError(
        "No hay LLM configurado. Define AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY "
        "(o OPENAI_API_KEY) en .env, o usa MOCK_MODE=true."
    )


def model_name() -> str:
    # En Azure el 'model' es el nombre del deployment
    if settings.azure_endpoint and settings.azure_api_key:
        return settings.azure_deployment
    return settings.openai_model


def analyst_model_name() -> str:
    if settings.azure_endpoint and settings.azure_api_key:
        return settings.azure_analyst_deployment or settings.azure_deployment
    return settings.openai_analyst_model or settings.openai_model


def chat(model: str, **kwargs):
    """chat.completions.create + registro de tokens para el reporte de costos."""
    from .costos import record_llm

    resp = get_client().chat.completions.create(model=model, **kwargs)
    record_llm(model, resp.usage)
    return resp
