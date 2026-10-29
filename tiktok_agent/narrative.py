"""Informe en prosa de analista experto.
- Con LLM: el modelo redacta a partir de las estadísticas (no ve datos crudos que no estén en ellas).
- Sin LLM (mock): redacción determinista por plantilla, útil para probar y como respaldo.
"""
from __future__ import annotations

import json
import re

from .config import settings

SECTIONS = [
    "Resumen ejecutivo", "Volumen y alcance de la conversación", "Quién publica", "Quién comenta",
    "Qué se está diciendo", "Sentimiento y emociones", "Evolución en el tiempo",
    "Riesgos y oportunidades", "Recomendaciones", "Notas metodológicas",
]

_SYSTEM = f"""Eres un analista senior de social listening e inteligencia de audiencias (10+ años, agencias y marcas en Latinoamérica).
Recibirás estadísticas calculadas sobre una muestra de videos y comentarios de TikTok sobre un tema.
Redacta un INFORME EN PROSA, en español, en Markdown, con estas secciones (## título) en este orden:
{chr(10).join('- ' + s for s in SECTIONS)}

Reglas:
- Prosa analítica, párrafos (no listas salvo en Recomendaciones). Tono de consultor experto: interpreta, no solo describas.
- Todo número que cites debe salir de las estadísticas. Nunca inventes datos, creadores ni citas.
- Cuantifica siempre: N, %, NSS, vistas. Menciona tamaños de muestra y, cuando compares grupos, si los IC95 se solapan (diferencia no concluyente).
- "Quién publica": tipos y tamaños de creadores (tiers), ángulos de contenido, postura de los creadores, quién concentra el alcance; nombra a los creadores más relevantes (@usuario) con su peso.
- "Quién comenta": perfiles de comentaristas (usuarios con experiencia, interesados en comprar, escépticos, expertos, etc.), su peso y cómo opina cada uno; recurrencia de comentaristas; spam/bots.
- "Qué se está diciendo": recorre los aspectos de mayor a menor peso, con su sentimiento y 1–2 citas textuales entre comillas con sus likes.
- Distingue sentimiento simple vs ponderado por likes (qué opinión AMPLIFICA la audiencia).
- Señala si la conversación está concentrada en pocos videos o creadores.
- Riesgos/oportunidades: concretos y accionables (reputación, desinformación, demanda insatisfecha, preguntas sin responder, aliados potenciales).
- Recomendaciones: 4–6 bullets accionables para una marca/organización interesada en el tema.
- Notas metodológicas: muestra no probabilística, cobertura de comentarios, cómo se interpretó el tema y cuántos videos se descartaron por no tratarlo (filtro_relevancia), limitaciones.
- El sentimiento solo tiene tres clases: positivo, negativo y neutral.
- Los IC95 existen solo para % positivo y % negativo; nunca atribuyas un intervalo al NSS. Si los IC95 se solapan, di que no se puede afirmar qué polo domina.
- Solo di que la audiencia "amplifica" críticas o elogios si el NSS ponderado difiere del simple en 5 puntos o más; si no, di que ambos coinciden.
- No afirmes riesgos (p. ej. desinformación) ni patrones (p. ej. "los negativos reciben más likes") que no se sigan de una cifra concreta de las estadísticas.
- Usa la interpretación del tema de filtro_relevancia; no describas contenido descartado como parte de la conversación.
- Extensión: 700–1100 palabras. Comienza directamente con '## Resumen ejecutivo'."""


def _slim(stats: dict) -> dict:
    s = {k: v for k, v in stats.items() if k not in ("videos", "costos", "saldo")}
    if stats.get("filtro_relevancia"):
        f = stats["filtro_relevancia"]
        s["filtro_relevancia"] = {**{k: v for k, v in f.items() if k != "descartados"}, "descartados": len(f["descartados"])}
    s["videos_mas_positivos"] = [{k: v[k] for k in ("author", "views", "nss", "angle", "url")} for v in stats["videos_mas_positivos"]]
    s["videos_mas_negativos"] = [{k: v[k] for k in ("author", "views", "nss", "angle", "url")} for v in stats["videos_mas_negativos"]]
    s["temporal"] = {**stats["temporal"], "comentarios_por_dia": stats["temporal"]["comentarios_por_dia"][-21:]}
    return s


def expert_report(stats: dict) -> str:
    if settings.mock or not settings.has_llm:
        return template_report(stats)
    from .llm import analyst_model_name, chat

    resp = chat(
        analyst_model_name(), temperature=0.3,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": f"Tema: {stats['topic']}\n\nEstadísticas (JSON):\n"
                                              + json.dumps(_slim(stats), ensure_ascii=False, default=str)}],
    )
    return resp.choices[0].message.content or template_report(stats)


# ------------------------------------------------------------------ plantilla (sin LLM)
def _f(n) -> str:
    return f"{n:,.0f}".replace(",", ".") if isinstance(n, (int, float)) else str(n)


def _tone(nss: float) -> str:
    return ("claramente positivo" if nss >= 30 else "moderadamente positivo" if nss >= 10 else
            "equilibrado" if nss > -10 else "moderadamente negativo" if nss > -30 else "claramente negativo")


def template_report(s: dict) -> str:
    v, r, se = s["volumen"], s["alcance"], s["sentimiento"]
    g, w = se["global"], se["ponderado_por_likes"]
    asp, per, tiers = s["aspectos"], s["comentaristas_por_perfil"], s["creadores_por_tier"]
    top_c, cont, conc, tmp = s["top_creadores"], s["contenido"], s["concentracion"], s["temporal"]
    t = s["topic"]
    P = []

    P.append("## Resumen ejecutivo")
    lead = asp[0] if asp else None
    subst = [a for a in asp if a["n"] >= 10 and not re.search(r"humor|otro|general", a["aspecto"])] or asp
    worst = min(subst, key=lambda a: a["nss"]) if subst else None
    best = max(subst, key=lambda a: a["nss"]) if subst else None
    P.append(
        f"La conversación sobre **{t}** en la muestra analizada ({v['videos']} videos, {_f(r['vistas'])} vistas y "
        f"{_f(v['comentarios_analizados_sin_spam'])} comentarios válidos de {_f(v['comentaristas_unicos'])} personas distintas) "
        f"tiene un tono **{_tone(g['nss'])}**, con un Net Sentiment Score de **{g['nss']}** "
        f"({g['pct']['positivo']}% positivo frente a {g['pct']['negativo']}% negativo). "
        + (f"Cuando se pondera por likes, el NSS pasa a **{w['nss']}**, lo que indica que la audiencia "
           f"{'amplifica más las opiniones favorables' if w['nss'] > g['nss'] + 5 else 'amplifica más las críticas' if w['nss'] < g['nss'] - 5 else 'amplifica ambos polos de forma similar'}. ")
        + (f"El aspecto que más conversación genera es «{lead['aspecto']}» ({lead['share_pct']}% de los comentarios); "
           f"el mejor valorado es «{best['aspecto']}» (NSS {best['nss']}) y el más crítico «{worst['aspecto']}» (NSS {worst['nss']})." if lead else "")
    )

    P.append("\n## Volumen y alcance de la conversación")
    P.append(
        f"Los {v['videos']} videos provienen de {v['creadores_unicos']} creadores y acumulan {_f(r['vistas'])} reproducciones, "
        f"{_f(r['likes'])} likes, {_f(r['compartidos'])} compartidos y {_f(r['guardados'])} guardados. "
        f"El engagement rate mediano es de {r['engagement_rate_mediano_pct']}% y la mediana de vistas por video es {_f(r['vistas_mediana_por_video'])}. "
        f"El alcance está {'muy concentrado' if r['concentracion_vistas_top3_pct'] > 60 else 'relativamente repartido'}: "
        f"los tres videos más vistos suman el {r['concentracion_vistas_top3_pct']}% de las reproducciones. "
        f"En total los videos reportan {_f(v['comentarios_reportados_en_videos'])} comentarios; se extrajeron {_f(v['comentarios_extraidos'])} "
        f"(cobertura del {v['cobertura_muestra_pct']}%), de los cuales {v['spam_detectado']} ({v['spam_pct']}%) se descartaron como spam o autopromoción."
    )

    P.append("\n## Quién publica")
    tier_txt = "; ".join(f"{x['tier']}: {x['videos']} video{'s' if x['videos'] != 1 else ''} y {x['pct_vistas']}% de las vistas" for x in tiers)
    lead_c = top_c[0] if top_c else None
    P.append(
        f"Por tamaño de cuenta, la distribución es: {tier_txt}. "
        f"Predominan los contenidos de tipo {', '.join(list(cont['angulos'])[:3])}, y entre los creadores la postura dominante hacia el tema es "
        f"«{next(iter(cont['postura_creadores']), 'n/d')}». Hay {cont['verificados']} cuentas verificadas y {r['videos_publicidad']} piezas marcadas como publicidad. "
        + (f"La voz con más alcance es @{lead_c['autor']} ({_f(lead_c['seguidores'])} seguidores, {lead_c['tipo'] or 'creador'}), "
           f"cuyo video suma {_f(lead_c['vistas'])} vistas con un ángulo {lead_c['angulo']} y una audiencia de NSS {lead_c['nss_comentarios']}. " if lead_c else "")
        + ("Por ángulo, la audiencia reacciona mejor a " + max(cont["nss_audiencia_por_angulo"], key=cont["nss_audiencia_por_angulo"].get)
           + " y peor a " + min(cont["nss_audiencia_por_angulo"], key=cont["nss_audiencia_por_angulo"].get) + "." if cont["nss_audiencia_por_angulo"] else "")
    )

    P.append("\n## Quién comenta")
    if per:
        main = [p for p in per if p["perfil"] != "spam/bot"][:4]
        P.append(
            f"Opinan {_f(v['comentaristas_unicos'])} cuentas únicas, con {v['comentarios_por_comentarista']} comentarios por persona en promedio; "
            f"{v['comentaristas_recurrentes']} de ellas comentan más de una vez y aportan el {v['pct_comentarios_de_recurrentes']}% del volumen. "
            "Por perfil, " + "; ".join(
                f"el perfil «{p['perfil']}» pesa el {p['pct']}% (NSS {p['nss']})" for p in main) + ". "
            + _persona_reading(per)
        )

    P.append("\n## Qué se está diciendo")
    for a in asp[:6]:
        pos = a["citas_positivas"][0] if a["citas_positivas"] else None
        neg = a["citas_negativas"][0] if a["citas_negativas"] else None
        P.append(
            f"**{a['aspecto'].capitalize()}** concentra el {a['share_pct']}% de la conversación ({a['n']} comentarios) con tono {_tone(a['nss'])} "
            f"(NSS {a['nss']}; emoción principal: {a['emocion_principal']}). "
            + (f"Del lado favorable: “{pos['text']}” ({pos['likes']} likes). " if pos else "")
            + (f"Del lado crítico: “{neg['text']}” ({neg['likes']} likes)." if neg else "")
        )

    P.append("\n## Sentimiento y emociones")
    emo = list(se["emociones"].items())[:3]
    P.append(
        f"Sobre {g['n']} comentarios, el {g['pct']['positivo']}% es positivo (IC95 {g['ci95_positivo'][0]}–{g['ci95_positivo'][1]}%), "
        f"el {g['pct']['negativo']}% negativo (IC95 {g['ci95_negativo'][0]}–{g['ci95_negativo'][1]}%) "
        f"y el {g['pct']['neutral']}% neutral. "
        + ("Los intervalos no se solapan, así que la diferencia entre positivos y negativos es robusta. "
           if g['ci95_positivo'][0] > g['ci95_negativo'][1] or g['ci95_negativo'][0] > g['ci95_positivo'][1]
           else "Los intervalos se solapan, así que no se puede afirmar con confianza qué polo domina. ")
        + f"En postura, un {se['postura']['a_favor']}% está a favor del tema y un {se['postura']['en_contra']}% en contra. "
        f"El {g['polarizacion_pct']}% de los comentarios tiene carga emocional intensa y el {se['sarcasmo_pct']}% usa sarcasmo. "
        f"Las emociones predominantes son " + ", ".join(f"{e} ({n})" for e, n in emo) + "."
    )

    P.append("\n## Evolución en el tiempo")
    if tmp["pico"]:
        P.append(
            f"Los videos de la muestra se publicaron entre {tmp['rango_videos'][0]} y {tmp['rango_videos'][1]}. "
            f"El día de mayor actividad en comentarios fue {tmp['pico']['fecha']} con {tmp['pico']['comentarios']} comentarios (NSS {tmp['pico']['nss']}). "
            f"La conversación está {conc['lectura']} entre videos (HHI {conc['hhi']}; el video con más comentarios aporta el {conc['pct_comentarios_video_top']}%)."
        )

    P.append("\n## Riesgos y oportunidades")
    P.append(
        (f"El principal foco de riesgo es «{worst['aspecto']}» (NSS {worst['nss']}), " if worst else "")
        + (f"y las preguntas más repetidas (p. ej. “{s['top_preguntas'][0]['text']}”) muestran demanda de información sin resolver. " if s["top_preguntas"] else "")
        + (f"La oportunidad está en «{best['aspecto']}» (NSS {best['nss']}), donde ya existe una base de opinión favorable que se puede amplificar." if best else "")
    )

    P.append("\n## Recomendaciones")
    if worst:
        P.append(f"- Atender de forma directa las críticas sobre «{worst['aspecto']}» con contenido claro y verificable.")
    if s["top_preguntas"]:
        P.append("- Producir contenido que responda a las preguntas frecuentes de la audiencia.")
    if best:
        P.append(f"- Amplificar testimonios reales sobre «{best['aspecto']}».")
    allies = [c for c in top_c if (c["nss_comentarios"] or 0) > 10]
    if allies:
        a = max(allies, key=lambda c: c["nss_comentarios"])
        P.append(f"- Evaluar alianzas con creadores de audiencia favorable (p. ej. @{a['autor']}, {_f(a['vistas'])} vistas, NSS {a['nss_comentarios']}).")
    P.append("- Monitorear semanalmente el NSS y los aspectos críticos para detectar cambios a tiempo.")

    P.append("\n## Notas metodológicas")
    P.append(s["metodologia"]["limitaciones"] + f" La cobertura de comentarios fue del {v['cobertura_muestra_pct']}% de los reportados."
             + (" **Este informe se generó en modo mock (datos sintéticos) con redacción por plantilla.**" if settings.mock else ""))
    return "\n".join(P)


def _persona_reading(per: list[dict]) -> str:
    valid = [p for p in per if p["perfil"] != "spam/bot" and p["n"] >= 5]
    if len(valid) < 2:
        return ""
    hi = max(valid, key=lambda p: p["nss"])
    lo = min(valid, key=lambda p: p["nss"])
    return (f"El perfil más favorable es «{hi['perfil']}» (NSS {hi['nss']}) y el más crítico «{lo['perfil']}» (NSS {lo['nss']}); "
            f"los comentarios de «{max(valid, key=lambda p: p['likes_promedio'])['perfil']}» son los que más likes reciben en promedio.")
