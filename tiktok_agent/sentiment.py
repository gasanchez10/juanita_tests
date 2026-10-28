"""Clasificación con LLM:
1) taxonomía de aspectos específica del tema (una llamada, para que las etiquetas sean consistentes)
2) cada comentario: sentimiento, score, emoción, sarcasmo, postura, aspecto, perfil del comentarista, spam
3) cada video: ángulo del contenido y postura del creador
En modo mock usa etiquetas deterministas (sin LLM).
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from .config import settings

LABELS = ("positivo", "negativo", "neutral", "mixto")
STANCES = ("a_favor", "en_contra", "neutral")
EMOTIONS = ("alegría", "enojo", "tristeza", "miedo", "sorpresa", "asco", "humor", "curiosidad", "confianza", "ninguna")
PERSONAS = (
    "usuario con experiencia propia", "potencial comprador/interesado", "escéptico/crítico",
    "experto/profesional", "seguidor del creador", "humor/entretenimiento", "spam/bot", "otro",
)
ANGLES = ("educativo/informativo", "testimonio/reseña", "opinión", "humor/entretenimiento",
          "promoción/publicidad", "noticia", "polémica/debate", "otro")


def _use_llm() -> bool:
    return settings.has_llm and not settings.mock


def _chat_json(system: str, user: str, temperature: float = 0) -> dict:
    from .llm import get_client, model_name

    resp = get_client().chat.completions.create(
        model=model_name(), temperature=temperature, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return json.loads(resp.choices[0].message.content or "{}")


# ------------------------------------------------------------------ taxonomía
def build_taxonomy(topic: str, comments: list[dict], videos: list[dict]) -> list[str]:
    if not _use_llm():
        from .tiktok_source import MOCK_ASPECTS
        return list(MOCK_ASPECTS)
    sample = sorted(comments, key=lambda c: c.get("likes", 0), reverse=True)[:120]
    sample += comments[:: max(1, len(comments) // 80)][:80]
    txt = "\n".join(f"- {c['text'][:200]}" for c in sample)
    caps = "\n".join(f"- {v['caption'][:150]}" for v in videos[:25])
    data = _chat_json(
        "Eres analista de social listening. A partir de la muestra, define de 5 a 9 ASPECTOS (subtemas) "
        "mutuamente excluyentes de los que la gente habla sobre el tema. Etiquetas cortas en español "
        "(1-4 palabras, minúsculas). No incluyas 'otro'. Devuelve JSON {\"aspects\":[...]}",
        f"Tema: {topic}\n\nCaptions:\n{caps}\n\nComentarios:\n{txt}",
    )
    aspects = [a.strip().lower() for a in data.get("aspects", []) if isinstance(a, str) and a.strip()][:9]
    return aspects or ["general"]


# ------------------------------------------------------------------ comentarios
def _comment_system(aspects: list[str]) -> str:
    return f"""Eres un analista experto en conversación digital en español latinoamericano: jerga de TikTok, emojis, sarcasmo, ironía.
Para CADA comentario devuelve, respecto al TEMA indicado:
- sentiment: {"|".join(LABELS)}  (preguntas sin postura = neutral)
- score: float -1..1
- emotion: {"|".join(EMOTIONS)}
- sarcasm: bool (si hay sarcasmo, el sentimiento es el real, no el literal)
- stance: {"|".join(STANCES)}  (postura hacia el tema, no hacia el creador)
- aspect: uno de {json.dumps(aspects + ["otro"], ensure_ascii=False)}
- persona: uno de {json.dumps(list(PERSONAS), ensure_ascii=False)}  (rol que se infiere SOLO del texto; nunca infieras edad, género, etnia, salud, religión ni política personal)
- spam: bool (autopromoción, 'sígueme', links, bots)
Devuelve SOLO JSON: {{"results":[{{"i":int,"sentiment":..,"score":..,"emotion":..,"sarcasm":..,"stance":..,"aspect":..,"persona":..,"spam":..}}]}} con un resultado por índice."""


def _norm(r: dict, aspects: list[str]) -> dict:
    pick = lambda v, opts, d: v if v in opts else d
    try:
        score = max(-1.0, min(1.0, float(r.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    return {
        "sentiment": pick(r.get("sentiment"), LABELS, "neutral"),
        "score": score,
        "emotion": pick(r.get("emotion"), EMOTIONS, "ninguna"),
        "sarcasm": bool(r.get("sarcasm", False)),
        "stance": pick(r.get("stance"), STANCES, "neutral"),
        "aspect": pick(str(r.get("aspect", "")).lower(), aspects + ["otro"], "otro"),
        "persona": pick(r.get("persona"), PERSONAS, "otro"),
        "spam": bool(r.get("spam", False)),
    }


_DEFAULT = {"sentiment": "neutral", "score": 0.0, "emotion": "ninguna", "sarcasm": False,
            "stance": "neutral", "aspect": "otro", "persona": "otro", "spam": False}


def _mock_label(text: str) -> dict:
    from .tiktok_source import MOCK_LABELS
    m = MOCK_LABELS.get(text)
    if not m:
        return dict(_DEFAULT)
    score = {"positivo": 0.7, "negativo": -0.7, "mixto": 0.1, "neutral": 0.0}[m["sentiment"]]
    emo = {"positivo": "alegría", "negativo": "enojo", "mixto": "confianza", "neutral": "curiosidad"}[m["sentiment"]]
    if m["aspect"] == "humor":
        emo = "humor"
    return {**_DEFAULT, **m, "score": score, "emotion": emo,
            "sarcasm": "astronauta" in text, "spam": m["persona"] == "spam/bot"}


def classify_comments(topic: str, comments: list[dict], aspects: list[str]) -> list[dict]:
    if not comments:
        return comments
    if not _use_llm():
        for c in comments:
            c.update(_mock_label(c["text"]))
        return comments

    system = _comment_system(aspects)
    items = list(enumerate(c["text"] for c in comments))
    bs = settings.sentiment_batch_size
    batches = [items[i: i + bs] for i in range(0, len(items), bs)]

    def run(batch):
        payload = "\n".join(f"[{i}] {t[:400]}" for i, t in batch)
        try:
            data = _chat_json(system, f"Tema: {topic}\n\nComentarios:\n{payload}")
        except Exception as e:  # un lote fallido no tumba el análisis
            print(f"  ! lote fallido: {e}")
            return {}
        out = {}
        for r in data.get("results", []):
            try:
                out[int(r["i"])] = _norm(r, aspects)
            except (KeyError, TypeError, ValueError):
                pass
        return out

    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for part in ex.map(run, batches):
            results.update(part)
    for i, c in enumerate(comments):
        c.update(results.get(i) or dict(_DEFAULT))
    return comments


# ------------------------------------------------------------------ videos
def classify_videos(topic: str, videos: list[dict]) -> list[dict]:
    if not videos:
        return videos
    if not _use_llm():
        from .tiktok_source import MOCK_ANGLES
        for v in videos:
            h = int(hashlib.md5(v["url"].encode()).hexdigest()[:6], 16)
            v["angle"] = "promoción/publicidad" if v.get("is_ad") else MOCK_ANGLES[h % len(MOCK_ANGLES)]
            v["creator_stance"] = STANCES[(h // 7) % 3]
            bio = v.get("author_bio", "").lower()
            v["creator_type"] = ("profesional de salud" if "nutricion" in bio else "influencer fitness" if "fitness" in bio
                                 else "creador de humor" if "humor" in bio else "reseñador" if "review" in bio else "usuario común")
        return videos

    payload = "\n".join(
        f"[{i}] @{v['author']} ({v['author_followers']} seguidores; bio: {v.get('author_bio','')[:80]}) :: {v['caption'][:300]}"
        for i, v in enumerate(videos))
    data = _chat_json(
        f"Clasifica cada video de TikTok según su caption y su creador, respecto al TEMA. "
        f"angle: uno de {json.dumps(list(ANGLES), ensure_ascii=False)}; "
        f"creator_stance: {'|'.join(STANCES)}; creator_type: categoría corta del creador inferida de bio/caption "
        f"(ej. 'medio de comunicación', 'marca', 'influencer fitness', 'profesional de salud', 'creador de humor', 'usuario común'). "
        "Devuelve SOLO JSON {\"results\":[{\"i\":int,\"angle\":..,\"creator_stance\":..,\"creator_type\":..}]}",
        f"Tema: {topic}\n\nVideos:\n{payload}",
    )
    by_i = {int(r.get("i", -1)): r for r in data.get("results", []) if isinstance(r, dict)}
    for i, v in enumerate(videos):
        r = by_i.get(i, {})
        v["angle"] = r.get("angle") if r.get("angle") in ANGLES else "otro"
        v["creator_stance"] = r.get("creator_stance") if r.get("creator_stance") in STANCES else "neutral"
        v["creator_type"] = str(r.get("creator_type") or "")[:40]
    return videos
