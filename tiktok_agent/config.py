"""Configuración centralizada (lee .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si", "sí"}


_PLACEHOLDERS = ("xxxx", "<tu-recurso>", "sk-...")


def _secret(name: str) -> str | None:
    """Lee una variable sensible; vacía o con el valor de ejemplo de .env.example → None."""
    v = (os.getenv(name) or "").strip()
    return None if not v or any(p in v for p in _PLACEHOLDERS) else v


@dataclass
class Settings:
    # --- Fuente de datos (Apify) ---
    apify_token: str | None = field(default_factory=lambda: _secret("APIFY_TOKEN"))
    apify_search_actor: str = field(default_factory=lambda: os.getenv("APIFY_SEARCH_ACTOR", "clockworks/tiktok-scraper"))
    apify_comments_actor: str = field(default_factory=lambda: os.getenv("APIFY_COMMENTS_ACTOR", "clockworks/tiktok-comments-scraper"))

    # --- LLM (Azure OpenAI / Foundry). Si no hay Azure, usa OPENAI_API_KEY ---
    azure_endpoint: str | None = field(default_factory=lambda: _secret("AZURE_OPENAI_ENDPOINT"))
    azure_api_key: str | None = field(default_factory=lambda: _secret("AZURE_OPENAI_API_KEY"))
    azure_api_version: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    azure_deployment: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"))
    # modelo más capaz para el informe en prosa y el agente (opcional; si no, usa el mismo)
    azure_analyst_deployment: str | None = field(default_factory=lambda: os.getenv("AZURE_OPENAI_ANALYST_DEPLOYMENT"))
    openai_analyst_model: str | None = field(default_factory=lambda: os.getenv("OPENAI_ANALYST_MODEL"))
    openai_api_key: str | None = field(default_factory=lambda: _secret("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # --- Comportamiento ---
    mock: bool = field(default_factory=lambda: _bool("MOCK_MODE"))
    output_dir: str = field(default_factory=lambda: os.getenv("OUTPUT_DIR", "outputs"))
    sentiment_batch_size: int = field(default_factory=lambda: int(os.getenv("SENTIMENT_BATCH_SIZE", "40")))

    @property
    def has_llm(self) -> bool:
        return bool((self.azure_endpoint and self.azure_api_key) or self.openai_api_key)


settings = Settings()
