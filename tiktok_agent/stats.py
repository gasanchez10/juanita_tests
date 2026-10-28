"""Estadísticas de social listening sobre videos + comentarios ya clasificados."""
from __future__ import annotations

import math
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime

from .sentiment import LABELS, PERSONAS

TIERS = [  # (nombre, mínimo de seguidores)
    ("mega (>1M)", 1_000_000), ("macro (500k–1M)", 500_000), ("mid (100k–500k)", 100_000),
    ("micro (10k–100k)", 10_000), ("nano (<10k)", 0),
]


def tier(followers: int) -> str:
    for name, lo in TIERS:
        if (followers or 0) >= lo:
            return name
    return TIERS[-1][0]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC 95% de Wilson para una proporción, en %."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * (c - h), 1), round(100 * (c + h), 1))


def sentiment_block(cs: list[dict], weighted: bool = False) -> dict:
    n = len(cs)
    cnt = Counter()
    for c in cs:
        cnt[c["sentiment"]] += (1 + c.get("likes", 0)) if weighted else 1
    tot = sum(cnt.values()) or 1
    pct = {k: round(100 * cnt[k] / tot, 1) for k in LABELS}
    out = {"n": n, "pct": pct, "nss": round(pct["positivo"] - pct["negativo"], 1)}
    if not weighted and n:
        scores = [c["score"] for c in cs]
        out.update({
            "counts": {k: cnt[k] for k in LABELS},
            "ci95_positivo": wilson(cnt["positivo"], n),
            "ci95_negativo": wilson(cnt["negativo"], n),
            "avg_score": round(st.mean(scores), 3),
            "std_score": round(st.pstdev(scores), 3),
            "polarizacion_pct": round(100 * sum(abs(s) >= 0.6 for s in scores) / n, 1),
        })
    return out


def _day(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _quotes(cs: list[dict], label: str, n: int = 2) -> list[dict]:
    xs = sorted((c for c in cs if c["sentiment"] == label), key=lambda c: c["likes"], reverse=True)
    seen, out = set(), []
    for c in xs:
        if c["text"] not in seen:
            seen.add(c["text"])
            out.append({"text": c["text"][:280], "likes": c["likes"], "video_url": c["video_url"]})
        if len(out) >= n:
            break
    return out


def compute_stats(topic: str, videos: list[dict], all_comments: list[dict], aspects: list[str]) -> dict:
    spam = [c for c in all_comments if c.get("spam")]
    cs = [c for c in all_comments if not c.get("spam")]  # todo el análisis de opinión excluye spam
    vid_by_url = {v["url"]: v for v in videos}
    by_video = defaultdict(list)
    for c in cs:
        by_video[c["video_url"]].append(c)

    # ---------------- volumen y alcance
    users = Counter(c["user"] for c in cs if c["user"])
    reported = sum(v["comments"] for v in videos)
    ers = [100 * (v["likes"] + v["comments"] + v["shares"] + v["saves"]) / v["views"] for v in videos if v["views"]]
    views_sorted = sorted((v["views"] for v in videos), reverse=True)
    total_views = sum(views_sorted) or 1
    volume = {
        "videos": len(videos),
        "creadores_unicos": len({v["author"] for v in videos}),
        "comentarios_reportados_en_videos": reported,
        "comentarios_extraidos": len(all_comments),
        "comentarios_analizados_sin_spam": len(cs),
        "spam_detectado": len(spam),
        "spam_pct": round(100 * len(spam) / len(all_comments), 1) if all_comments else 0,
        "cobertura_muestra_pct": round(100 * len(all_comments) / reported, 1) if reported else None,
        "comentaristas_unicos": len(users),
        "comentarios_por_comentarista": round(len(cs) / len(users), 2) if users else 0,
        "comentaristas_recurrentes": sum(1 for n in users.values() if n > 1),
        "pct_comentarios_de_recurrentes": round(100 * sum(n for n in users.values() if n > 1) / len(cs), 1) if cs else 0,
        "likes_en_comentarios": sum(c["likes"] for c in cs),
        "respuestas_en_comentarios": sum(c.get("replies", 0) for c in cs),
    }
    reach = {
        "vistas": sum(v["views"] for v in videos),
        "likes": sum(v["likes"] for v in videos),
        "compartidos": sum(v["shares"] for v in videos),
        "guardados": sum(v["saves"] for v in videos),
        "vistas_mediana_por_video": int(st.median(views_sorted)) if views_sorted else 0,
        "engagement_rate_mediano_pct": round(st.median(ers), 2) if ers else None,
        "engagement_rate_promedio_pct": round(st.mean(ers), 2) if ers else None,
        "concentracion_vistas_top1_pct": round(100 * views_sorted[0] / total_views, 1) if views_sorted else 0,
        "concentracion_vistas_top3_pct": round(100 * sum(views_sorted[:3]) / total_views, 1) if views_sorted else 0,
        "videos_publicidad": sum(1 for v in videos if v.get("is_ad")),
    }

    # ---------------- sentimiento global
    sentiment = {
        "global": sentiment_block(cs),
        "ponderado_por_likes": sentiment_block(cs, weighted=True),
        "emociones": dict(Counter(c["emotion"] for c in cs).most_common()),
        "sarcasmo_pct": round(100 * sum(c.get("sarcasm", False) for c in cs) / len(cs), 1) if cs else 0,
        "postura": {k: round(100 * sum(c.get("stance") == k for c in cs) / len(cs), 1) if cs else 0
                    for k in ("a_favor", "en_contra", "neutral")},
    }

    # ---------------- quién opina (comentaristas)
    personas = []
    for p in PERSONAS:
        sub = [c for c in all_comments if c.get("persona") == p]
        if not sub:
            continue
        b = sentiment_block(sub)
        personas.append({"perfil": p, "n": len(sub), "pct": round(100 * len(sub) / len(all_comments), 1),
                         "nss": b["nss"], "pct_positivo": b["pct"]["positivo"], "pct_negativo": b["pct"]["negativo"],
                         "likes_promedio": round(st.mean(c["likes"] for c in sub), 1)})
    personas.sort(key=lambda x: x["n"], reverse=True)

    # ---------------- quién publica (creadores)
    tiers = []
    for name, _ in TIERS:
        vs = [v for v in videos if tier(v["author_followers"]) == name]
        if not vs:
            continue
        sub = [c for v in vs for c in by_video.get(v["url"], [])]
        tiers.append({"tier": name, "videos": len(vs), "vistas": sum(v["views"] for v in vs),
                      "pct_vistas": round(100 * sum(v["views"] for v in vs) / total_views, 1),
                      "nss_comentarios": sentiment_block(sub)["nss"] if sub else None})
    creators = []
    for v in sorted(videos, key=lambda v: v["views"], reverse=True)[:10]:
        sub = by_video.get(v["url"], [])
        creators.append({"autor": v["author"], "seguidores": v["author_followers"], "tier": tier(v["author_followers"]),
                         "verificado": v.get("author_verified"), "tipo": v.get("creator_type", ""),
                         "angulo": v.get("angle"), "postura_creador": v.get("creator_stance"),
                         "vistas": v["views"], "nss_comentarios": sentiment_block(sub)["nss"] if sub else None,
                         "url": v["url"], "caption": v["caption"][:140]})
    content = {
        "angulos": dict(Counter(v.get("angle", "otro") for v in videos).most_common()),
        "postura_creadores": dict(Counter(v.get("creator_stance", "neutral") for v in videos).most_common()),
        "tipos_creador": dict(Counter(v.get("creator_type") or "n/d" for v in videos).most_common(8)),
        "verificados": sum(1 for v in videos if v.get("author_verified")),
        "hashtags": Counter(h.lower() for v in videos for h in v["hashtags"]).most_common(15),
    }
    # sentimiento de la audiencia según el ángulo del video
    angle_sent = {}
    for a in content["angulos"]:
        sub = [c for v in videos if v.get("angle") == a for c in by_video.get(v["url"], [])]
        if sub:
            angle_sent[a] = sentiment_block(sub)["nss"]
    content["nss_audiencia_por_angulo"] = angle_sent

    # ---------------- qué se dice (aspectos)
    asp = []
    for a in aspects + ["otro"]:
        sub = [c for c in cs if c.get("aspect") == a]
        if not sub:
            continue
        b = sentiment_block(sub)
        asp.append({"aspecto": a, "n": len(sub), "share_pct": round(100 * len(sub) / len(cs), 1),
                    "nss": b["nss"], "pct": b["pct"], "likes_totales": sum(c["likes"] for c in sub),
                    "emocion_principal": Counter(c["emotion"] for c in sub).most_common(1)[0][0],
                    "citas_positivas": _quotes(sub, "positivo"), "citas_negativas": _quotes(sub, "negativo"),
                    "citas_neutras": _quotes(sub, "neutral", 1)})
    asp.sort(key=lambda x: x["n"], reverse=True)

    # ---------------- tiempo
    vday = Counter(d for d in (_day(v["created_at"]) for v in videos) if d)
    cday = defaultdict(list)
    for c in cs:
        d = _day(c.get("created_at"))
        if d:
            cday[d].append(c)
    timeline = [{"fecha": d, "comentarios": len(x), "nss": sentiment_block(x)["nss"]} for d, x in sorted(cday.items())]
    peak = max(timeline, key=lambda t: t["comentarios"]) if timeline else None
    temporal = {
        "rango_videos": [min(vday), max(vday)] if vday else None,
        "videos_por_fecha": dict(sorted(vday.items())),
        "comentarios_por_dia": timeline[-45:],
        "pico": peak,
    }

    # ---------------- concentración de la conversación
    per_vid = sorted((len(x) for x in by_video.values()), reverse=True)
    hhi = sum((n / len(cs)) ** 2 for n in per_vid) if cs else 0
    concentration = {
        "pct_comentarios_video_top": round(100 * per_vid[0] / len(cs), 1) if per_vid else 0,
        "hhi": round(hhi, 3),  # 1 = un solo video concentra todo
        "lectura": "concentrada" if hhi > 0.25 else "moderada" if hhi > 0.1 else "distribuida",
    }

    # ---------------- videos (tabla completa)
    vrows = []
    for v in videos:
        sub = by_video.get(v["url"], [])
        b = sentiment_block(sub) if sub else None
        vrows.append({**v, "tier": tier(v["author_followers"]),
                      "engagement_rate": round(100 * (v["likes"] + v["comments"] + v["shares"] + v["saves"]) / v["views"], 2) if v["views"] else 0,
                      "n_comentarios_analizados": len(sub), "nss": b["nss"] if b else None,
                      "pct_positivo": b["pct"]["positivo"] if b else None, "pct_negativo": b["pct"]["negativo"] if b else None})
    rated = [v for v in vrows if v["nss"] is not None and v["n_comentarios_analizados"] >= 5]

    return {
        "topic": topic,
        "volumen": volume,
        "alcance": reach,
        "sentimiento": sentiment,
        "comentaristas_por_perfil": personas,
        "creadores_por_tier": tiers,
        "top_creadores": creators,
        "contenido": content,
        "aspectos": asp,
        "temporal": temporal,
        "concentracion": concentration,
        "videos_mas_positivos": sorted(rated, key=lambda v: v["nss"], reverse=True)[:3],
        "videos_mas_negativos": sorted(rated, key=lambda v: v["nss"])[:3],
        "top_comentarios_positivos": _quotes(cs, "positivo", 5),
        "top_comentarios_negativos": _quotes(cs, "negativo", 5),
        "top_preguntas": [{"text": c["text"][:200], "likes": c["likes"]} for c in
                          sorted((c for c in cs if "?" in c["text"]), key=lambda c: c["likes"], reverse=True)[:5]],
        "videos": vrows,
        "metodologia": {
            "fuente": "TikTok vía Apify (búsqueda por palabra clave/hashtag + comentarios top por video)",
            "clasificacion": "LLM por lotes con taxonomía de aspectos generada para el tema; spam excluido del análisis de opinión",
            "nss": "Net Sentiment Score = %positivo − %negativo (−100 a 100)",
            "ic95": "Intervalo de confianza de Wilson al 95% sobre la muestra analizada",
            "limitaciones": "Muestra no probabilística: depende del ranking de búsqueda de TikTok y de los comentarios más visibles; "
                            "no representa a toda la población de TikTok ni a la opinión pública general.",
        },
    }
