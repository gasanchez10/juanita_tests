"""Clasificación con LLM:
0) plan de búsqueda: interpreta el tema (desambigua), genera consultas y criterios de inclusión/exclusión
1) cada video: relevancia respecto al tema interpretado, ángulo, postura y tipo de creador
2) taxonomía de aspectos específica del tema (una llamada, para que las etiquetas sean consistentes)
3) cada comentario: sentimiento, score, emoción, sarcasmo, postura, aspecto, perfil del comentarista, spam
En modo mock usa etiquetas deterministas (sin LLM).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from .config import settings

LABELS = ("positivo", "negativo", "neutral")
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


def _chat_json(system: str, user: str, temperature: float = 0, analyst: bool = False) -> dict:
    """analyst=True usa el modelo fuerte: para decisiones de pocos ítems donde un error sesga todo (plan, relevancia)."""
    from .llm import analyst_model_name, chat, model_name

    resp = chat(analyst_model_name() if analyst else model_name(), temperature=temperature, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return json.loads(resp.choices[0].message.content or "{}")


def _parallel(fn, items: list, workers: int = 6) -> list:
    """map en hilos conservando el contexto (el tracker de costos vive en un contextvar)."""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(contextvars.copy_context().run, fn, it) for it in items]
        return [f.result() for f in futures]


def topic_brief(topic: str, plan: dict | None) -> str:
    """Bloque de texto con el tema y su interpretación, para todos los prompts."""
    if not plan:
        return f"Tema: {topic}"
    lines = [f"Tema: {topic}", f"Interpretación: {plan.get('interpretacion', topic)}"]
    if plan.get("incluir"):
        lines.append("Cuenta como parte del tema: " + "; ".join(plan["incluir"]))
    if plan.get("excluir"):
        lines.append("NO es parte del tema: " + "; ".join(plan["excluir"]))
    return "\n".join(lines)


# ------------------------------------------------------------------ plan de búsqueda
def plan_search(topic: str, contexto: str = "") -> dict:
    """Interpreta el tema y genera las consultas de búsqueda. Para #hashtags solo se busca el hashtag."""
    topic = topic.strip()
    base = {"interpretacion": contexto or topic, "consultas": [topic], "incluir": [], "excluir": []}
    if not _use_llm():
        return base
    data = _chat_json(
        "Eres analista senior de social listening en Latinoamérica y planeas una búsqueda en TikTok.\n"
        "1) interpretacion: explica en una o dos frases QUÉ conversación quiere estudiar el usuario. Desambigua "
        "el sentido según el contexto, el lugar y el uso común en Colombia/Latinoamérica (por ejemplo, "
        "'inseguridad' junto a un barrio o ciudad es delincuencia y seguridad ciudadana, no inseguridad emocional; "
        "una marca que también es palabra común se refiere a la marca). Si el usuario dio contexto, manda el contexto.\n"
        "2) consultas: de 2 a 4 búsquedas cortas (2–5 palabras) como las escribiría alguien en TikTok, en el idioma "
        "del tema. La primera es la consulta original tal cual; las demás cubren sinónimos y subtemas concretos "
        "(p. ej. robos, atracos, hurtos) sin salirse del lugar o del alcance pedido.\n"
        "3) incluir: 3 a 6 criterios concretos de lo que SÍ cuenta como parte del tema.\n"
        "4) excluir: 2 a 5 sentidos o contenidos que NO cuentan aunque compartan palabras (homónimos, otros "
        "lugares, contenido genérico con hashtags de moda).\n"
        "Devuelve SOLO JSON {\"interpretacion\": str, \"consultas\": [str], \"incluir\": [str], \"excluir\": [str]}",
        f"Tema: {topic}" + (f"\nContexto del usuario: {contexto}" if contexto else ""), analyst=True,
    )
    consultas = [q.strip() for q in data.get("consultas", []) if isinstance(q, str) and q.strip()]
    if topic.startswith("#"):
        consultas = [topic]
    else:
        consultas = list(dict.fromkeys([topic] + consultas))[:4]
    clean = lambda xs: [x.strip() for x in xs if isinstance(x, str) and x.strip()][:6]
    return {"interpretacion": str(data.get("interpretacion") or base["interpretacion"]).strip(),
            "consultas": consultas, "incluir": clean(data.get("incluir", [])), "excluir": clean(data.get("excluir", []))}


# ------------------------------------------------------------------ taxonomía
def build_taxonomy(topic: str, comments: list[dict], videos: list[dict], plan: dict | None = None) -> list[str]:
    if not _use_llm():
        from .tiktok_source import MOCK_ASPECTS
        return list(MOCK_ASPECTS)
    sample = sorted(comments, key=lambda c: c.get("likes", 0), reverse=True)[:120]
    sample += comments[:: max(1, len(comments) // 80)][:80]
    txt = "\n".join(f"- {c['text'][:200]}" for c in sample)
    caps = "\n".join(f"- {v['caption'][:150]}" for v in videos[:25])
    data = _chat_json(
        "Eres analista de social listening. A partir de la muestra, define de 5 a 9 ASPECTOS (subtemas) "
        "mutuamente excluyentes de los que la gente habla sobre el tema, TAL COMO ESTÁ INTERPRETADO. "
        "Prefiere subtemas concretos del tema (p. ej. tipos de hecho, actores, causas, respuestas institucionales) "
        "sobre categorías genéricas. Etiquetas cortas en español (1-4 palabras, minúsculas). No incluyas 'otro'. "
        "Devuelve JSON {\"aspects\":[...]}",
        f"{topic_brief(topic, plan)}\n\nCaptions:\n{caps}\n\nComentarios:\n{txt}",
    )
    aspects = [a.strip().lower() for a in data.get("aspects", []) if isinstance(a, str) and a.strip()][:9]
    return aspects or ["general"]


# ------------------------------------------------------------------ comentarios
def _comment_system(aspects: list[str]) -> str:
    return f"""Eres un analista experto en conversación digital en español latinoamericano: jerga de TikTok, emojis, sarcasmo, ironía.
Para CADA comentario devuelve, respecto al TEMA indicado (usa su interpretación):
- sentiment: {"|".join(LABELS)}. Si mezcla elogio y crítica, elige la polaridad que domina; si ninguna domina, o es una pregunta o dato sin postura, neutral.
- score: float -1..1
- emotion: {"|".join(EMOTIONS)}
- sarcasm: bool (si hay sarcasmo, el sentimiento es el real, no el literal)
- stance: {"|".join(STANCES)}  (postura hacia el tema, no hacia el creador)
- aspect: uno de {json.dumps(aspects + ["otro"], ensure_ascii=False)} ("otro" si el comentario no trata del tema)
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
    score = {"positivo": 0.7, "negativo": -0.7, "neutral": 0.0}[m["sentiment"]]
    emo = {"positivo": "alegría", "negativo": "enojo", "neutral": "curiosidad"}[m["sentiment"]]
    if m["aspect"] == "humor":
        emo = "humor"
    return {**_DEFAULT, **m, "score": score, "emotion": emo,
            "sarcasm": "astronauta" in text, "spam": m["persona"] == "spam/bot"}


def classify_comments(topic: str, comments: list[dict], aspects: list[str], plan: dict | None = None) -> list[dict]:
    if not comments:
        return comments
    if not _use_llm():
        for c in comments:
            c.update(_mock_label(c["text"]))
        return comments

    system = _comment_system(aspects)
    brief = topic_brief(topic, plan)
    items = list(enumerate(c["text"] for c in comments))
    bs = settings.sentiment_batch_size
    batches = [items[i: i + bs] for i in range(0, len(items), bs)]

    def run(batch):
        payload = "\n".join(f"[{i}] {t[:400]}" for i, t in batch)
        try:
            data = _chat_json(system, f"{brief}\n\nComentarios:\n{payload}")
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
    for part in _parallel(run, batches):
        results.update(part)
    for i, c in enumerate(comments):
        c.update(results.get(i) or dict(_DEFAULT))
    return comments


# ------------------------------------------------------------------ videos
def _video_system() -> str:
    return (
        "Clasifica cada video de TikTok según su caption, hashtags y creador, respecto al TEMA y su interpretación.\n"
        "- relevante: true SOLO si el video trata directamente del tema interpretado (su asunto principal es el tema, "
        "o es un caso concreto del tema). false si solo comparte una palabra, usa el hashtag como relleno, habla de otro "
        "lugar u otro sentido de la palabra, o es contenido genérico. Si el caption está vacío, decide por hashtags y creador; "
        "si aun así no hay señal, false. Lee la jerga regional y coloquial con su sentido local (p. ej. en Colombia "
        "'ratoneros' son ladrones, 'fleteo' es un tipo de robo); no descartes un video solo por su tono sensacionalista.\n"
        "- motivo: máximo 12 palabras explicando la decisión de relevancia.\n"
        f"- angle: uno de {json.dumps(list(ANGLES), ensure_ascii=False)}\n"
        f"- creator_stance: {'|'.join(STANCES)}\n"
        "- creator_type: categoría corta del creador inferida de bio/caption (ej. 'medio de comunicación', 'marca', "
        "'político', 'entidad pública', 'influencer', 'usuario común').\n"
        "Devuelve SOLO JSON {\"results\":[{\"i\":int,\"relevante\":bool,\"motivo\":str,\"angle\":..,\"creator_stance\":..,\"creator_type\":..}]}"
    )


def classify_videos(topic: str, videos: list[dict], plan: dict | None = None) -> list[dict]:
    """Agrega relevante, motivo_relevancia, angle, creator_stance y creator_type a cada video."""
    if not videos:
        return videos
    if not _use_llm():
        from .tiktok_source import MOCK_ANGLES
        for v in videos:
            h = int(hashlib.md5(v["url"].encode()).hexdigest()[:6], 16)
            v["relevante"], v["motivo_relevancia"] = True, "modo mock"
            v["angle"] = "promoción/publicidad" if v.get("is_ad") else MOCK_ANGLES[h % len(MOCK_ANGLES)]
            v["creator_stance"] = STANCES[(h // 7) % 3]
            bio = v.get("author_bio", "").lower()
            v["creator_type"] = ("profesional de salud" if "nutricion" in bio else "influencer fitness" if "fitness" in bio
                                 else "creador de humor" if "humor" in bio else "reseñador" if "review" in bio else "usuario común")
        return videos

    system, brief = _video_system(), topic_brief(topic, plan)
    batches = [list(enumerate(videos))[i: i + 40] for i in range(0, len(videos), 40)]

    def run(batch):
        payload = "\n".join(
            f"[{i}] @{v['author']} ({v['author_followers']} seguidores; bio: {v.get('author_bio','')[:80]}) "
            f"hashtags: {' '.join('#' + h for h in (v.get('hashtags') or [])[:10])} :: {v['caption'][:300]}"
            for i, v in batch)
        try:
            data = _chat_json(system, f"{brief}\n\nVideos:\n{payload}", analyst=True)
        except Exception as e:
            print(f"  ! lote de videos fallido: {e}")
            return {}
        return {int(r.get("i", -1)): r for r in data.get("results", []) if isinstance(r, dict)}

    by_i: dict[int, dict] = {}
    for part in _parallel(run, batches):
        by_i.update(part)
    for i, v in enumerate(videos):
        r = by_i.get(i)
        # si el LLM no devolvió el video (lote fallido), se conserva: mejor un falso positivo que perder datos
        v["relevante"] = bool(r.get("relevante", True)) if r else True
        v["motivo_relevancia"] = str((r or {}).get("motivo") or ("sin clasificar" if not r else ""))[:120]
        r = r or {}
        v["angle"] = r.get("angle") if r.get("angle") in ANGLES else "otro"
        v["creator_stance"] = r.get("creator_stance") if r.get("creator_stance") in STANCES else "neutral"
        v["creator_type"] = str(r.get("creator_type") or "")[:40]
    return videos
