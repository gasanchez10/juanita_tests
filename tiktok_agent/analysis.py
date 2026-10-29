"""Pipeline: buscar videos -> comentarios -> taxonomía -> clasificación -> estadísticas -> informe experto."""
from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from . import costos
from .config import settings
from .narrative import expert_report
from .sentiment import _use_llm, build_taxonomy, classify_comments, classify_videos, plan_search
from .stats import compute_stats
from .tiktok_source import ORDENES, get_source, sort_items

RELEVANCE_OVERFETCH = 2  # con LLM se buscan el doble de videos y se descartan los que no tratan del tema
_ORDEN_TXT = {"relevancia": "relevancia", "mas_likeados": "más likeados", "mas_recientes": "más recientes"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "tema"


def _log(msg: str):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel abre bien tildes/emojis
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict, tuple)) else v for k, v in r.items()})


def _f(n) -> str:
    return f"{n:,.0f}".replace(",", ".") if isinstance(n, (int, float)) else str(n)


def render_markdown(s: dict) -> str:
    v, r, g, w = s["volumen"], s["alcance"], s["sentimiento"]["global"], s["sentimiento"]["ponderado_por_likes"]
    L = [f"# TikTok · {s['topic']}",
         f"_Generado {s['generated_at']} · modo {s['mode']} · {s['elapsed_s']} s_", "",
         "## Tablero", "",
         "| Métrica | Valor |", "|---|---:|",
         f"| Videos / creadores | {v['videos']} / {v['creadores_unicos']} |",
         f"| Vistas totales | {_f(r['vistas'])} |",
         f"| Comentarios reportados → analizados | {_f(v['comentarios_reportados_en_videos'])} → {_f(v['comentarios_analizados_sin_spam'])} |",
         f"| Comentaristas únicos | {_f(v['comentaristas_unicos'])} |",
         f"| Spam descartado | {v['spam_detectado']} ({v['spam_pct']}%) |",
         f"| **NSS** (ponderado por likes) | **{g['nss']}** ({w['nss']}) |",
         f"| Positivo / Negativo / Neutral | {g['pct']['positivo']}% / {g['pct']['negativo']}% / {g['pct']['neutral']}% |",
         f"| IC95 positivo · negativo | {g['ci95_positivo'][0]}–{g['ci95_positivo'][1]}% · {g['ci95_negativo'][0]}–{g['ci95_negativo'][1]}% |",
         f"| Engagement rate mediano | {r['engagement_rate_mediano_pct']}% |", "",
         *_render_busqueda(s), *_render_costos(s),
         s["informe"], "",
         "---", "# Anexos estadísticos", "",
         "## Aspectos", "| Aspecto | N | % | NSS | Pos % | Neg % | Emoción |", "|---|---:|---:|---:|---:|---:|---|"]
    for a in s["aspectos"]:
        L.append(f"| {a['aspecto']} | {a['n']} | {a['share_pct']} | {a['nss']} | {a['pct']['positivo']} | {a['pct']['negativo']} | {a['emocion_principal']} |")
    L += ["", "## Perfiles de comentaristas", "| Perfil | N | % | NSS | Likes prom. |", "|---|---:|---:|---:|---:|"]
    for p in s["comentaristas_por_perfil"]:
        L.append(f"| {p['perfil']} | {p['n']} | {p['pct']} | {p['nss']} | {p['likes_promedio']} |")
    L += ["", "## Creadores por tamaño", "| Tier | Videos | % vistas | NSS audiencia |", "|---|---:|---:|---:|"]
    for t in s["creadores_por_tier"]:
        L.append(f"| {t['tier']} | {t['videos']} | {t['pct_vistas']} | {t['nss_comentarios']} |")
    L += ["", "## Top creadores", "| Creador | Seguidores | Tipo | Ángulo | Postura | Vistas | NSS | URL |", "|---|---:|---|---|---|---:|---:|---|"]
    for c in s["top_creadores"]:
        L.append(f"| @{c['autor']} | {_f(c['seguidores'])} | {c['tipo']} | {c['angulo']} | {c['postura_creador']} | {_f(c['vistas'])} | {c['nss_comentarios']} | {c['url']} |")
    L += ["", "## Emociones", ", ".join(f"{k} ({n})" for k, n in s["sentimiento"]["emociones"].items()),
          "", "## Hashtags", ", ".join(f"#{h} ({n})" for h, n in s["contenido"]["hashtags"]), ""]
    return "\n".join(L)


def _render_busqueda(s: dict) -> list[str]:
    p, f = s.get("parametros"), s.get("filtro_relevancia")
    if not p or not f:
        return []
    L = ["## Búsqueda", "",
         f"- **Interpretación del tema:** {f['interpretacion']}",
         f"- **Consultas:** {', '.join(f['consultas'])}",
         f"- **Orden:** videos por {_ORDEN_TXT[p['orden_videos']]} · comentarios por {_ORDEN_TXT[p['orden_comentarios']]}",
         f"- **Filtro de relevancia:** {f['videos_relevantes']} de {f['videos_encontrados']} videos trataban del tema; "
         f"se analizaron {f['videos_usados']}.", ""]
    if f["descartados"]:
        L += ["**Videos descartados por no tratar del tema**", "",
              "| Creador | Motivo | Caption |", "|---|---|---|"]
        L += [f"| @{d['autor']} | {d['motivo']} | {d['caption'].replace('|', '/').replace(chr(10), ' ')} |"
              for d in f["descartados"]]
        L.append("")
    return L


def _render_costos(s: dict) -> list[str]:
    c, sd = s.get("costos"), s.get("saldo")
    if not c:
        return []
    llm, ap = c["llm"], c["apify"]
    L = ["## Costo de la corrida", "", "| Concepto | Valor |", "|---|---:|",
         f"| Tokens LLM (entrada / salida) | {_f(llm['tokens_entrada'])} / {_f(llm['tokens_salida'])} |",
         f"| Costo LLM estimado | USD {llm['costo_usd_estimado']} |",
         f"| Costo Apify | USD {ap['costo_usd']} |",
         f"| **Total estimado** | **USD {c['total_usd_estimado']}** |"]
    a = (sd or {}).get("apify") or {}
    if a.get("disponible_usd") is not None:
        L.append(f"| Saldo Apify disponible | USD {a['disponible_usd']} de {a['limite_mes_usd']} "
                 f"(~{a['analisis_estandar_restantes']} análisis estándar) |")
    L.append("")
    for al in (sd or {}).get("alertas", []):
        L += [f"> ⚠️ {al}", ""]
    return L


def analyze_topic(topic: str, max_videos: int = 20, comments_per_video: int = 50, save: bool = True,
                  orden_videos: str = "relevancia", orden_comentarios: str = "relevancia", contexto: str = "") -> dict:
    if orden_videos not in ORDENES or orden_comentarios not in ORDENES:
        raise ValueError(f"orden debe ser uno de {ORDENES}")
    t0 = time.time()
    token = costos.start()
    try:
        src = get_source()
        _log(f"Interpretando el tema '{topic}'…")
        plan = plan_search(topic, contexto)
        _log(f"Interpretación: {plan['interpretacion']} · consultas: {plan['consultas']}")
        fetch = min(100, max_videos * (RELEVANCE_OVERFETCH if _use_llm() else 1))
        found = src.search_videos(topic, max_videos=fetch, orden=orden_videos, consultas=plan["consultas"])
        _log(f"{len(found)} videos encontrados. Filtrando por relevancia…")
        classify_videos(topic, found, plan)
        relevant = [v for v in found if v.get("relevante", True)]
        if found and not relevant:
            raise RuntimeError(
                f"Ninguno de los {len(found)} videos encontrados trata de '{topic}' según la interpretación "
                f"«{plan['interpretacion']}». No se descargaron comentarios (no hubo costo de comentarios). "
                "Prueba otra formulación, un #hashtag o agrega `contexto`.")
        videos = sort_items(relevant, orden_videos)[:max_videos]
        _log(f"{len(relevant)} relevantes; se analizan {len(videos)}. Extrayendo comentarios…")
        comments = (src.get_comments([v["url"] for v in videos], per_video=comments_per_video, orden=orden_comentarios)
                    if videos and comments_per_video else [])
        _log(f"{len(comments)} comentarios. Construyendo taxonomía y clasificando…")
        aspects = build_taxonomy(topic, comments, videos, plan)
        classify_comments(topic, comments, aspects, plan)
        _log("Calculando estadísticas…")
        stats = compute_stats(topic, videos, comments, aspects)
        stats.update({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": "mock" if settings.mock else "live", "aspect_taxonomy": aspects,
            "parametros": {"topic": topic, "contexto": contexto, "max_videos": max_videos,
                           "comments_per_video": comments_per_video, "orden_videos": orden_videos,
                           "orden_comentarios": orden_comentarios},
            "filtro_relevancia": {
                **plan, "videos_encontrados": len(found), "videos_relevantes": len(relevant), "videos_usados": len(videos),
                "descartados": [{"autor": v["author"], "url": v["url"], "caption": v["caption"][:120],
                                 "motivo": v.get("motivo_relevancia", "")} for v in found if not v.get("relevante", True)]},
        })
        _log("Redactando informe experto…")
        stats["informe"] = expert_report(stats)
    finally:
        cost_summary = costos.stop(token)
    stats["costos"] = cost_summary
    stats["saldo"] = costos.saldo() if not settings.mock else {
        "apify": None, "openai": None, "necesita_recarga": False, "alertas": [], "nota": "modo mock: sin consumo"}
    stats["elapsed_s"] = round(time.time() - t0, 1)
    _log(f"Costo estimado: USD {cost_summary['total_usd_estimado']} "
         f"({cost_summary['llm']['tokens_total']} tokens LLM, USD {cost_summary['apify']['costo_usd']} Apify)")

    if save:
        out = Path(settings.output_dir) / f"{datetime.now():%Y%m%d-%H%M%S}_{_slug(topic)}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(render_markdown(stats), encoding="utf-8")
        (out / "report.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        _write_csv(out / "videos.csv", stats["videos"])
        _write_csv(out / "comments.csv", comments)
        stats["output_dir"] = str(out.resolve())
        _log(f"Listo en {stats['elapsed_s']} s → {out}")
    return stats


def compact(stats: dict) -> dict:
    """Lo que ve el agente: el informe completo + cifras clave (sin tablas crudas)."""
    keys = ("topic", "mode", "generated_at", "parametros", "costos", "saldo", "volumen", "alcance", "sentimiento",
            "comentaristas_por_perfil", "creadores_por_tier", "concentracion", "aspect_taxonomy", "top_preguntas",
            "informe", "output_dir")
    out = {k: stats.get(k) for k in keys}
    f = stats.get("filtro_relevancia")
    out["filtro_relevancia"] = {k: v for k, v in f.items() if k != "descartados"} | {
        "descartados": len(f["descartados"])} if f else None
    out["aspectos"] = [{k: a[k] for k in ("aspecto", "n", "share_pct", "nss", "citas_positivas", "citas_negativas")} for a in stats["aspectos"]]
    out["top_creadores"] = stats["top_creadores"][:6]
    out["contenido"] = {k: stats["contenido"][k] for k in ("angulos", "postura_creadores", "tipos_creador")}
    return out
