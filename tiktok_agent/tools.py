"""Tools del agente. Mismas funciones + schemas se reutilizan en:
- el agente local (function calling de Azure OpenAI)
- la API FastAPI (OpenAPI tool en Azure AI Foundry)
- FunctionTool del SDK de Foundry Agent Service
"""
from __future__ import annotations

from .analysis import analyze_topic, compact
from .sentiment import build_taxonomy, classify_comments
from .tiktok_source import get_source


def analyze_tiktok_topic(topic: str, max_videos: int = 20, comments_per_video: int = 50,
                         orden_videos: str = "relevancia", orden_comentarios: str = "relevancia", contexto: str = "") -> dict:
    """Análisis completo de un tema: videos, URLs, métricas, comentarios, sentimiento, temas, costos y saldo."""
    max_videos = max(1, min(int(max_videos), 100))
    comments_per_video = max(0, min(int(comments_per_video), 300))
    return compact(analyze_topic(topic, max_videos, comments_per_video, orden_videos=orden_videos,
                                 orden_comentarios=orden_comentarios, contexto=contexto))


def search_tiktok_videos(topic: str, max_videos: int = 10, orden_videos: str = "relevancia") -> dict:
    """Busca videos por palabra clave o #hashtag. Devuelve URL, autor, caption y métricas."""
    vids = get_source().search_videos(topic, max_videos=max(1, min(int(max_videos), 50)), orden=orden_videos)
    return {"topic": topic, "count": len(vids), "videos": vids}


def get_tiktok_comments(video_urls: list[str], comments_per_video: int = 50, topic: str = "") -> dict:
    """Trae comentarios de videos específicos y les aplica sentimiento."""
    cs = get_source().get_comments(video_urls[:20], per_video=max(1, min(int(comments_per_video), 300)))
    t = topic or "el video"
    classify_comments(t, cs, build_taxonomy(t, cs, []))
    from .stats import sentiment_block
    valid = [c for c in cs if not c.get("spam")]
    return {"count": len(cs), "sentimiento": sentiment_block(valid) if valid else None,
            "comments": [{k: c.get(k) for k in ("text", "likes", "sentiment", "aspect", "persona", "stance", "video_url")}
                         for c in sorted(valid, key=lambda c: c["likes"], reverse=True)[:150]]}


TOOL_FUNCTIONS = {
    "analyze_tiktok_topic": analyze_tiktok_topic,
    "search_tiktok_videos": search_tiktok_videos,
    "get_tiktok_comments": get_tiktok_comments,
}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "analyze_tiktok_topic",
        "description": "Análisis completo de un tema en TikTok: busca videos, extrae comentarios, calcula sentimiento (NSS, distribución, emociones), temas, quejas, elogios, alertas y guarda reporte (md/json/csv). Úsala para preguntas generales sobre qué se dice de un tema.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Palabra clave o #hashtag, ej. 'Petro reforma', '#skincare'"},
            "max_videos": {"type": "integer", "default": 20, "description": "1-100"},
            "comments_per_video": {"type": "integer", "default": 50, "description": "0-300"},
            "orden_videos": {"type": "string", "enum": ["relevancia", "mas_likeados", "mas_recientes"], "default": "relevancia"},
            "orden_comentarios": {"type": "string", "enum": ["relevancia", "mas_likeados", "mas_recientes"], "default": "relevancia"},
            "contexto": {"type": "string", "description": "Opcional: qué significa el tema y qué excluir, ej. 'delincuencia y robos en la localidad de Bosa, Bogotá'"},
        }, "required": ["topic"]},
    }},
    {"type": "function", "function": {
        "name": "search_tiktok_videos",
        "description": "Solo lista videos (URLs, autor, caption, vistas, likes, hashtags) de un tema, sin comentarios. Rápida y barata.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string"},
            "max_videos": {"type": "integer", "default": 10},
            "orden_videos": {"type": "string", "enum": ["relevancia", "mas_likeados", "mas_recientes"], "default": "relevancia"},
        }, "required": ["topic"]},
    }},
    {"type": "function", "function": {
        "name": "get_tiktok_comments",
        "description": "Comentarios con sentimiento de una o varias URLs de TikTok concretas.",
        "parameters": {"type": "object", "properties": {
            "video_urls": {"type": "array", "items": {"type": "string"}},
            "comments_per_video": {"type": "integer", "default": 50},
            "topic": {"type": "string", "description": "Tema de referencia para el sentimiento"},
        }, "required": ["video_urls"]},
    }},
]
