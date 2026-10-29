"""Costos y saldo: tokens del LLM, cargos de Apify por corrida y crédito disponible.

Cada análisis abre un `Tracker` (contextvar); `llm.chat()` y `ApifySource._run()` le reportan su consumo.
Los hilos que clasifican en paralelo deben correr con `contextvars.copy_context()` para heredar el tracker.
"""
from __future__ import annotations

import contextvars
import math
import threading
from functools import lru_cache

from .config import settings

# USD por millón de tokens (entrada, salida). Precios públicos de OpenAI; Azure suele cobrar lo mismo.
# Si usas otro modelo, agrégalo aquí: sin precio el costo queda en None (los tokens sí se cuentan).
LLM_PRICES_PER_M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}

# Respaldo si no se puede leer la tarifa del actor en Apify (plan FREE, octubre 2026)
_FALLBACK_EVENT_PRICES = {
    "result": 0.0037, "mobile-filter-sorting-applied": 0.0013, "filter-applied": 0.0013, "actor-start": 0.001,
}
_FALLBACK_COMMENT_PRICE = 0.00125
STANDARD_RUN = (20, 50)  # videos × comentarios del "análisis estándar", para saber cuántos alcanzan con el saldo

_current: contextvars.ContextVar["Tracker | None"] = contextvars.ContextVar("costos_tracker", default=None)


def _as_dict(obj) -> dict:
    """apify-client ≥2 devuelve modelos pydantic; 1.x devuelve dicts."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    return obj.model_dump(by_alias=True, mode="json")


def llm_price(model: str) -> tuple[float, float] | None:
    m = (model or "").lower()
    # el más largo primero: "gpt-4.1-mini" antes que "gpt-4.1"
    for name in sorted(LLM_PRICES_PER_M, key=len, reverse=True):
        if m == name or m.startswith(name + "-") or m.startswith(name):
            return LLM_PRICES_PER_M[name]
    return None


class Tracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.llm: dict[str, dict] = {}
        self.apify: list[dict] = []

    def add_llm(self, model: str, usage) -> None:
        pt = getattr(usage, "prompt_tokens", 0)
        ct = getattr(usage, "completion_tokens", 0)
        with self._lock:
            m = self.llm.setdefault(model, {"llamadas": 0, "tokens_entrada": 0, "tokens_salida": 0})
            m["llamadas"] += 1
            m["tokens_entrada"] += pt or 0
            m["tokens_salida"] += ct or 0

    def add_apify(self, actor: str, run) -> None:
        r = _as_dict(run)
        events = r.get("chargedEventCounts") or {}
        prices = actor_event_prices(actor)
        cost = sum(n * prices.get(ev, 0) for ev, n in events.items()) if events else r.get("usageTotalUsd")
        with self._lock:
            self.apify.append({"actor": actor, "run_id": r.get("id"), "eventos_cobrados": events,
                               "costo_usd": round(cost, 4) if cost is not None else None})

    def summary(self) -> dict:
        por_modelo = {}
        for model, m in self.llm.items():
            p = llm_price(model)
            cost = (m["tokens_entrada"] * p[0] + m["tokens_salida"] * p[1]) / 1e6 if p else None
            por_modelo[model] = {**m, "tokens_total": m["tokens_entrada"] + m["tokens_salida"],
                                 "costo_usd_estimado": round(cost, 4) if cost is not None else None}
        llm_cost = [m["costo_usd_estimado"] for m in por_modelo.values()]
        llm_total = round(sum(c for c in llm_cost if c is not None), 4)
        apify_total = round(sum(a["costo_usd"] or 0 for a in self.apify), 4)
        return {
            "llm": {"por_modelo": por_modelo,
                    "tokens_entrada": sum(m["tokens_entrada"] for m in por_modelo.values()),
                    "tokens_salida": sum(m["tokens_salida"] for m in por_modelo.values()),
                    "tokens_total": sum(m["tokens_total"] for m in por_modelo.values()),
                    "costo_usd_estimado": llm_total,
                    "precio_desconocido": [k for k, m in por_modelo.items() if m["costo_usd_estimado"] is None]},
            "apify": {"corridas": self.apify, "costo_usd": apify_total},
            "total_usd_estimado": round(llm_total + apify_total, 4),
        }


def start() -> contextvars.Token:
    return _current.set(Tracker())


def stop(token: contextvars.Token) -> dict:
    tracker = _current.get()
    _current.reset(token)
    return tracker.summary() if tracker else Tracker().summary()


def record_llm(model: str, usage) -> None:
    t = _current.get()
    if t:
        t.add_llm(model, usage)


def record_apify(actor: str, run) -> None:
    t = _current.get()
    if t:
        t.add_apify(actor, run)


# ------------------------------------------------------------------ tarifas y saldo de Apify
def _apify_client():
    from apify_client import ApifyClient
    return ApifyClient(settings.apify_token)


@lru_cache(maxsize=1)
def apify_plan() -> str:
    try:
        return (_as_dict(_apify_client().user().get()).get("plan") or {}).get("id") or "FREE"
    except Exception:
        return "FREE"


@lru_cache(maxsize=8)
def actor_event_prices(actor: str) -> dict[str, float]:
    """Precio por evento del actor según el plan de la cuenta (pay-per-event)."""
    if not settings.apify_token:
        return dict(_FALLBACK_EVENT_PRICES)
    try:
        info = _as_dict(_apify_client().actor(actor).get())
        events = (info.get("pricingInfos") or [{}])[-1].get("pricingPerEvent", {}).get("actorChargeEvents", {})
        plan = apify_plan()
        out = {}
        for name, ev in events.items():
            tiers = ev.get("eventTieredPricingUsd") or {}
            price = (tiers.get(plan) or tiers.get("FREE") or {}).get("tieredEventPriceUsd", ev.get("eventPriceUsd"))
            if price is not None:
                out[name] = float(price)
        return out or dict(_FALLBACK_EVENT_PRICES)
    except Exception:
        return dict(_FALLBACK_EVENT_PRICES)


def estimate_apify_usd(videos_fetched: int, comments: int, sorted_search: bool = False, n_queries: int = 1) -> float:
    vp = actor_event_prices(settings.apify_search_actor)
    cp = actor_event_prices(settings.apify_comments_actor)
    v = videos_fetched * (vp.get("result", 0) + (vp.get("mobile-filter-sorting-applied", 0) if sorted_search else 0))
    starts = (n_queries + 1) * vp.get("actor-start", 0)
    return round(v + comments * cp.get("result", _FALLBACK_COMMENT_PRICE) + starts, 4)


def saldo() -> dict:
    """Crédito disponible. Apify: real (API de límites). OpenAI: no expone saldo prepago con una API key normal."""
    std = estimate_apify_usd(STANDARD_RUN[0] * 2, STANDARD_RUN[0] * STANDARD_RUN[1])
    out: dict = {"apify": None, "openai": {
        "disponible_usd": None,
        "nota": "OpenAI no expone el saldo prepago con una API key normal. "
                "Revísalo en https://platform.openai.com/settings/organization/billing"}}
    alertas = []
    if settings.apify_token:
        try:
            lim = _as_dict(_apify_client().user().limits())
            used = (lim.get("current") or {}).get("monthlyUsageUsd")
            cap = (lim.get("limits") or {}).get("maxMonthlyUsageUsd")
            avail = round(cap - used, 2) if used is not None and cap is not None else None
            out["apify"] = {
                "plan": apify_plan(), "uso_mes_usd": round(used, 2) if used is not None else None,
                "limite_mes_usd": cap, "disponible_usd": avail,
                "ciclo_termina": (lim.get("monthlyUsageCycle") or {}).get("endAt"),
                "costo_analisis_estandar_usd": std,
                "analisis_estandar_restantes": math.floor(avail / std) if avail is not None and std else None,
            }
            if avail is not None and avail < std:
                alertas.append(f"Apify: quedan USD {avail}, menos de lo que cuesta un análisis estándar "
                               f"(~USD {std}). Recarga o sube de plan en https://console.apify.com/billing")
        except Exception as e:
            out["apify"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    out["necesita_recarga"] = bool(alertas)
    out["alertas"] = alertas
    return out
