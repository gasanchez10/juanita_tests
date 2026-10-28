"""Pipeline: buscar videos -> comentarios -> taxonomía -> clasificación -> estadísticas -> informe experto."""
from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from .config import settings
from .narrative import expert_report
from .sentiment import build_taxonomy, classify_comments, classify_videos
from .stats import compute_stats
from .tiktok_source import get_source


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
         f"| Positivo / Negativo / Neutral / Mixto | {g['pct']['positivo']}% / {g['pct']['negativo']}% / {g['pct']['neutral']}% / {g['pct']['mixto']}% |",
         f"| IC95 positivo · negativo | {g['ci95_positivo'][0]}–{g['ci95_positivo'][1]}% · {g['ci95_negativo'][0]}–{g['ci95_negativo'][1]}% |",
         f"| Engagement rate mediano | {r['engagement_rate_mediano_pct']}% |", "",
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


def analyze_topic(topic: str, max_videos: int = 20, comments_per_video: int = 50, save: bool = True) -> dict:
    t0 = time.time()
    src = get_source()
    _log(f"Buscando videos de '{topic}'…")
    videos = src.search_videos(topic, max_videos=max_videos)
    _log(f"{len(videos)} videos. Extrayendo comentarios…")
    comments = src.get_comments([v["url"] for v in videos], per_video=comments_per_video) if videos and comments_per_video else []
    _log(f"{len(comments)} comentarios. Construyendo taxonomía y clasificando…")
    aspects = build_taxonomy(topic, comments, videos)
    classify_comments(topic, comments, aspects)
    classify_videos(topic, videos)
    _log("Calculando estadísticas…")
    stats = compute_stats(topic, videos, comments, aspects)
    stats.update({"generated_at": datetime.now().isoformat(timespec="seconds"),
                  "mode": "mock" if settings.mock else "live", "aspect_taxonomy": aspects})
    _log("Redactando informe experto…")
    stats["informe"] = expert_report(stats)
    stats["elapsed_s"] = round(time.time() - t0, 1)

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
    keys = ("topic", "mode", "volumen", "alcance", "sentimiento", "comentaristas_por_perfil", "creadores_por_tier",
            "concentracion", "aspect_taxonomy", "top_preguntas", "informe", "output_dir")
    out = {k: stats.get(k) for k in keys}
    out["aspectos"] = [{k: a[k] for k in ("aspecto", "n", "share_pct", "nss", "citas_positivas", "citas_negativas")} for a in stats["aspectos"]]
    out["top_creadores"] = stats["top_creadores"][:6]
    out["contenido"] = {k: stats["contenido"][k] for k in ("angulos", "postura_creadores", "tipos_creador")}
    return out
