"""Fuente de datos TikTok.

Implementación actual: Apify (actores de clockworks). La interfaz `TikTokSource`
permite cambiar el proveedor (EnsembleData, TikAPI, Research API...) sin tocar
el resto del agente.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .config import settings


# ---------------------------------------------------------------- modelos
def normalize_video(raw: dict[str, Any]) -> dict[str, Any]:
    author = raw.get("authorMeta") or {}
    hashtags = [h.get("name") for h in (raw.get("hashtags") or []) if isinstance(h, dict) and h.get("name")]
    created = raw.get("createTimeISO")
    if not created and raw.get("createTime"):
        created = datetime.fromtimestamp(int(raw["createTime"]), tz=timezone.utc).isoformat()
    return {
        "video_id": str(raw.get("id", "")),
        "url": raw.get("webVideoUrl") or raw.get("url") or "",
        "caption": raw.get("text") or "",
        "created_at": created,
        "author": author.get("name") or author.get("uniqueId") or "",
        "author_nickname": author.get("nickName") or "",
        "author_followers": author.get("fans") or 0,
        "author_verified": bool(author.get("verified")),
        "author_bio": author.get("signature") or "",
        "views": raw.get("playCount") or 0,
        "likes": raw.get("diggCount") or 0,
        "comments": raw.get("commentCount") or 0,
        "shares": raw.get("shareCount") or 0,
        "saves": raw.get("collectCount") or 0,
        "hashtags": hashtags,
        "music": (raw.get("musicMeta") or {}).get("musicName"),
        "is_ad": bool(raw.get("isAd")),
        "location": raw.get("locationCreated") or raw.get("textLanguage") or "",
    }


def normalize_comment(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "comment_id": str(raw.get("cid", "")),
        "video_url": raw.get("videoWebUrl") or "",
        "text": raw.get("text") or "",
        "likes": raw.get("diggCount") or 0,
        "replies": raw.get("replyCommentTotal") or 0,
        "created_at": raw.get("createTimeISO"),
        "user": raw.get("uniqueId") or raw.get("uid") or "",
    }


ORDENES = ("relevancia", "mas_likeados", "mas_recientes")
_APIFY_SORT = {"relevancia": "MOST_RELEVANT", "mas_likeados": "MOST_LIKED", "mas_recientes": "LATEST"}
COMMENT_OVERFETCH = 2  # el actor de comentarios no ordena: se trae el doble y se ordena aquí


def sort_items(items: list[dict], orden: str) -> list[dict]:
    """relevancia conserva el orden de TikTok; los otros ordenan por likes o por fecha (desc)."""
    if orden == "mas_likeados":
        return sorted(items, key=lambda x: x.get("likes") or 0, reverse=True)
    if orden == "mas_recientes":
        return sorted(items, key=lambda x: x.get("created_at") or "", reverse=True)
    return list(items)


def comments_to_fetch(per_video: int, orden: str) -> int:
    return per_video if orden == "relevancia" else min(300, per_video * COMMENT_OVERFETCH)


def _top_per_video(comments: list[dict], per_video: int, orden: str) -> list[dict]:
    by_video: dict[str, list[dict]] = {}
    for c in comments:
        by_video.setdefault(c["video_url"], []).append(c)
    return [c for cs in by_video.values() for c in sort_items(cs, orden)[:per_video]]


class TikTokSource(Protocol):
    def search_videos(self, topic: str, max_videos: int = 20, orden: str = "relevancia",
                      consultas: list[str] | None = None) -> list[dict]: ...
    def get_comments(self, video_urls: list[str], per_video: int = 50, orden: str = "relevancia") -> list[dict]: ...


# ---------------------------------------------------------------- Apify
class ApifySource:
    def __init__(self, token: str):
        from apify_client import ApifyClient

        self.client = ApifyClient(token)

    def _run(self, actor: str, run_input: dict) -> list[dict]:
        run = self.client.actor(actor).call(run_input=run_input)
        if not run:
            raise RuntimeError(f"El actor {actor} no devolvió ejecución")
        # apify-client ≥2 devuelve un modelo `Run`; 1.x devuelve un dict
        dataset_id = run["defaultDatasetId"] if isinstance(run, dict) else run.default_dataset_id
        from .costos import record_apify
        record_apify(actor, run)
        items = list(self.client.dataset(dataset_id).iterate_items())
        return [i for i in items if "errorCode" not in i and "error" not in i]

    def search_videos(self, topic: str, max_videos: int = 20, orden: str = "relevancia",
                      consultas: list[str] | None = None) -> list[dict]:
        """Hashtag: el actor no ordena, se ordena aquí. Palabra clave: orden nativo de TikTok (add-on con costo)
        y, si hay varias consultas, `max_videos` se reparte entre ellas."""
        topic = topic.strip()
        queries = consultas or [topic]
        run_input: dict[str, Any] = {
            "resultsPerPage": max_videos,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
            "shouldDownloadSlideshowImages": False,
        }
        if topic.startswith("#"):
            run_input["hashtags"] = [topic.lstrip("#")]
        else:
            run_input["searchQueries"] = queries
            run_input["resultsPerPage"] = -(-max_videos // len(queries))
            if orden != "relevancia":
                run_input["videoSearchSorting"] = _APIFY_SORT[orden]
        raw = self._run(settings.apify_search_actor, run_input)
        videos = [normalize_video(r) for r in raw]
        seen, out = set(), []
        for v in videos:
            if v["url"] and v["url"] not in seen:
                seen.add(v["url"])
                out.append(v)
        return sort_items(out, orden)[:max_videos]

    def get_comments(self, video_urls: list[str], per_video: int = 50, orden: str = "relevancia") -> list[dict]:
        if not video_urls:
            return []
        raw = self._run(
            settings.apify_comments_actor,
            {"postURLs": video_urls, "commentsPerPost": comments_to_fetch(per_video, orden), "maxRepliesPerComment": 0},
        )
        return _top_per_video([normalize_comment(r) for r in raw if r.get("text")], per_video, orden)


# ---------------------------------------------------------------- Mock
# (texto, aspecto, sentimiento, perfil, postura). El clasificador mock usa esta tabla
# como "verdad" para que el pipeline completo sea verificable sin LLM.
MOCK_ASPECTS = ["precio", "resultados", "seguridad y efectos", "credibilidad del contenido", "disponibilidad y compra", "humor"]
MOCK_COMMENTS: list[tuple[str, str, str, str, str]] = [
    ("Por ese precio vale totalmente la pena", "precio", "positivo", "usuario con experiencia propia", "a_favor"),
    ("Demasiado caro para lo que es 😒", "precio", "negativo", "escéptico/crítico", "en_contra"),
    ("¿Cuánto cuesta en Colombia?", "precio", "neutral", "potencial comprador/interesado", "neutral"),
    ("Lo uso hace 3 meses y los resultados son increíbles 🔥", "resultados", "positivo", "usuario con experiencia propia", "a_favor"),
    ("Yo lo probé y no me funcionó para nada", "resultados", "negativo", "usuario con experiencia propia", "en_contra"),
    ("¿En cuánto tiempo se ven resultados?", "resultados", "neutral", "potencial comprador/interesado", "neutral"),
    ("Funciona pero hay que ser constante, no es magia", "resultados", "positivo", "usuario con experiencia propia", "a_favor"),
    ("Soy nutricionista y sí, tiene buena evidencia científica", "seguridad y efectos", "positivo", "experto/profesional", "a_favor"),
    ("A mí me dio efectos secundarios, cuidado", "seguridad y efectos", "negativo", "usuario con experiencia propia", "en_contra"),
    ("¿Tiene efectos secundarios?", "seguridad y efectos", "neutral", "potencial comprador/interesado", "neutral"),
    ("Como médico: consulten antes, no es para todo el mundo", "seguridad y efectos", "neutral", "experto/profesional", "neutral"),
    ("Por fin alguien que explica con evidencia 👏", "credibilidad del contenido", "positivo", "seguidor del creador", "a_favor"),
    ("Esto es pura desinformación, publicidad disfrazada", "credibilidad del contenido", "negativo", "escéptico/crítico", "en_contra"),
    ("Sí claro, y yo soy astronauta 🙄", "credibilidad del contenido", "negativo", "escéptico/crítico", "en_contra"),
    ("¿Fuente?", "credibilidad del contenido", "neutral", "escéptico/crítico", "neutral"),
    ("Lo conseguí fácil en la tienda de la esquina", "disponibilidad y compra", "positivo", "usuario con experiencia propia", "a_favor"),
    ("No se consigue en ningún lado 😩", "disponibilidad y compra", "negativo", "potencial comprador/interesado", "neutral"),
    ("¿Dónde lo compro? link porfa", "disponibilidad y compra", "neutral", "potencial comprador/interesado", "neutral"),
    ("jajaja el final 😂😂", "humor", "positivo", "humor/entretenimiento", "neutral"),
    ("Vine por los comentarios 🍿", "humor", "neutral", "humor/entretenimiento", "neutral"),
    ("sígueme y te sigo 🔥🔥", "otro", "neutral", "spam/bot", "neutral"),
    ("👇👇 mira mi perfil gana dinero", "otro", "neutral", "spam/bot", "neutral"),
]
MOCK_LABELS = {t: {"aspect": a, "sentiment": s, "persona": p, "stance": st} for t, a, s, p, st in MOCK_COMMENTS}
MOCK_ANGLES = ["educativo/informativo", "testimonio/reseña", "opinión", "humor/entretenimiento", "promoción/publicidad", "noticia", "polémica/debate"]


class MockSource:
    """Datos sintéticos deterministas por tema, para probar sin llaves."""

    def _rng(self, key: str) -> random.Random:
        return random.Random(int(hashlib.md5(key.encode()).hexdigest()[:8], 16))

    def search_videos(self, topic: str, max_videos: int = 20, orden: str = "relevancia",
                      consultas: list[str] | None = None) -> list[dict]:
        rng = self._rng(topic)
        tag = topic.lstrip("#").replace(" ", "").lower()
        now = datetime.now(timezone.utc)
        out = []
        for _ in range(max_videos):
            vid = str(7_400_000_000_000_000_000 + rng.randint(0, 10**15))
            followers = int(rng.lognormvariate(10.5, 2.0))
            author = f"creador_{rng.randint(100, 999)}"
            views = int(followers * rng.uniform(0.3, 3) + rng.lognormvariate(8, 1.5))
            hook = rng.choice(["Lo que nadie te dice de", "Mi opinión honesta sobre", "Probé 30 días", "La verdad sobre",
                               "Mitos y verdades de", "No compres", "Reacción a"])
            out.append({
                "video_id": vid,
                "url": f"https://www.tiktok.com/@{author}/video/{vid}",
                "caption": f"{hook} {topic} #{tag} #{rng.choice(['fyp', 'parati', 'viral', 'colombia', 'salud', 'tips'])}",
                "created_at": (now - timedelta(days=rng.randint(0, 45), hours=rng.randint(0, 23))).isoformat(),
                "author": author,
                "author_nickname": author.replace("_", " ").title(),
                "author_followers": followers,
                "author_verified": followers > 500_000 and rng.random() < 0.5,
                "author_bio": rng.choice(["Coach fitness 💪", "Nutricionista | tips", "Vlogs y humor", "Reviews honestas", ""]),
                "views": views,
                "likes": int(views * rng.uniform(0.02, 0.12)),
                "comments": int(views * rng.uniform(0.002, 0.012)),
                "shares": int(views * rng.uniform(0.001, 0.02)),
                "saves": int(views * rng.uniform(0.001, 0.03)),
                "hashtags": [tag, rng.choice(["fyp", "parati", "viral", "colombia", "salud", "tips"])],
                "music": "sonido original",
                "is_ad": rng.random() < 0.08,
                "location": "CO",
            })
        return sort_items(out, orden)

    def get_comments(self, video_urls: list[str], per_video: int = 50, orden: str = "relevancia") -> list[dict]:
        wanted, per_video = per_video, comments_to_fetch(per_video, orden)
        out = []
        user_pool = [f"user{n}" for n in range(1000, 1000 + max(30, len(video_urls) * per_video * 3))]
        for url in video_urls:
            rng = self._rng(url)
            weights = [rng.uniform(0.3, 2.0) for _ in MOCK_COMMENTS]
            base = datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 30))
            for j in range(per_video):
                text = rng.choices([c[0] for c in MOCK_COMMENTS], weights=weights)[0]
                out.append({
                    "comment_id": f"{url[-8:]}-{j}",
                    "video_url": url,
                    "text": text,
                    "likes": max(0, int(rng.paretovariate(1.1)) - 1),
                    "replies": rng.randint(0, 5),
                    "created_at": (base + timedelta(hours=int(rng.expovariate(1 / 30)))).isoformat(),
                    "user": rng.choice(user_pool),
                })
        return _top_per_video(out, wanted, orden)


def get_source() -> TikTokSource:
    if settings.mock:
        return MockSource()
    if not settings.apify_token:
        raise RuntimeError("Falta APIFY_TOKEN en .env (o activa MOCK_MODE=true).")
    return ApifySource(settings.apify_token)
