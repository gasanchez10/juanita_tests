"""Diagnóstico del entorno (Python, paquetes, llaves, conectividad) sin exponer secretos.
Lo usan `run.py doctor` (consola) y `GET /diagnostico` (API)."""
from __future__ import annotations

import os
import sys


def _mask(v: str | None) -> str:
    return f"{v[:4]}…{v[-3:]}" if v and len(v) > 10 else "(vacío)"


def run_checks() -> list[dict]:
    """Devuelve [{"estado": "ok"|"aviso"|"error", "mensaje": str}, …]."""
    out: list[dict] = []

    def line(status: bool | None, msg: str):
        out.append({"estado": "ok" if status else ("aviso" if status is None else "error"), "mensaje": msg})

    line(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (requiere ≥ 3.10)")
    for mod in ("apify_client", "openai", "dotenv", "fastapi", "markdown"):
        try:
            __import__(mod)
            line(True, f"paquete {mod}")
        except ImportError:
            line(False, f"paquete {mod} no instalado → pip install -r requirements.txt")

    line(os.path.exists(".env"), ".env existe" if os.path.exists(".env") else ".env no existe → cp .env.example .env")
    from .config import settings

    line(None if settings.mock else True, f"MOCK_MODE={'true (datos sintéticos)' if settings.mock else 'false (datos reales)'}")

    # Apify (config.py ya convierte valores vacíos o de ejemplo en None)
    if settings.apify_token:
        try:
            from apify_client import ApifyClient
            me = ApifyClient(settings.apify_token).user().get() or {}
            # apify-client ≥2 devuelve modelos pydantic; 1.x devuelve dicts
            username = me.get("username") if isinstance(me, dict) else getattr(me, "username", None)
            line(True, f"Apify autenticado como '{username or '?'}' (token {_mask(settings.apify_token)})")
        except Exception as e:
            line(False, f"Apify rechazó el token {_mask(settings.apify_token)}: {type(e).__name__}: {str(e)[:120]}")
    else:
        line(False if not settings.mock else None, "APIFY_TOKEN vacío o placeholder")

    # LLM
    azure = bool(settings.azure_endpoint and settings.azure_api_key)
    if azure or settings.openai_api_key:
        from .llm import analyst_model_name, get_client, model_name
        prov = f"Azure ({settings.azure_endpoint})" if azure else "OpenAI"
        for label, m in {"clasificación": model_name(), "analista": analyst_model_name()}.items():
            try:
                r = get_client().chat.completions.create(model=m, max_tokens=5,
                                                         messages=[{"role": "user", "content": "di ok"}])
                line(True, f"LLM {label}: {prov} · deployment '{m}' responde ('{(r.choices[0].message.content or '').strip()}')")
            except Exception as e:
                line(False, f"LLM {label}: deployment '{m}' falló → {type(e).__name__}: {str(e)[:160]}")
    else:
        line(False if not settings.mock else None, "LLM no configurado (AZURE_OPENAI_* u OPENAI_API_KEY)")

    try:
        os.makedirs(settings.output_dir, exist_ok=True)
        line(os.access(settings.output_dir, os.W_OK), f"carpeta de salida '{settings.output_dir}' escribible")
    except OSError as e:
        line(False, f"carpeta de salida: {e}")
    return out
