"""API HTTP de TikTok Pulse con Swagger en /docs.

- Uso humano: diagnóstico, análisis, lista de reportes, vista HTML y descarga de archivos.
- Uso por agentes: /analyze, /search y /comments (su /openapi.json se registra en Azure AI Foundry como OpenAPI tool).

    uvicorn tiktok_agent.api:app --port 8000      →  http://localhost:8000/docs
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import tools
from .config import settings

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
MAX_SIN_CONFIRMAR = 3000  # comentarios (30 videos × 100); por encima se exige confirmar_costo
ARCHIVOS = {"report.md": "text/markdown", "report.json": "application/json",
            "videos.csv": "text/csv", "comments.csv": "text/csv"}
_ID_RE = re.compile(r"^\d{8}-\d{6}_[a-z0-9-]+$")
_mock_lock = threading.Lock()  # MOCK_MODE es global: una corrida a la vez si se alterna por petición

app = FastAPI(
    title="TikTok Pulse",
    version="0.2.0",
    description=(
        "Agente de **social listening en TikTok**: dado un tema, busca videos, extrae comentarios, "
        "clasifica sentimiento, aspectos y perfiles con un LLM y redacta un informe de analista.\n\n"
        "**Cómo empezar**\n"
        "1. `GET /diagnostico`: verifica que las llaves funcionen.\n"
        "2. `POST /analyze` con `modo_prueba: true`: corrida gratis con datos sintéticos.\n"
        "3. `POST /analyze` con `modo_prueba: false`: corrida real (cuesta dinero, tarda 1–5 min).\n"
        "4. Abre el enlace `enlaces.ver` de la respuesta en el navegador para leer el reporte organizado.\n\n"
        "Guía completa: [/guia](/guia) · Cómo funciona por dentro: [/como-funciona](/como-funciona)"
    ),
    servers=[{"url": os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")}],
    openapi_tags=[
        {"name": "1. Inicio", "description": "Estado del servicio y diagnóstico de llaves."},
        {"name": "2. Análisis", "description": "Corre el agente sobre un tema."},
        {"name": "3. Reportes", "description": "Consulta, lee y descarga reportes ya generados."},
        {"name": "4. Herramientas del agente",
         "description": "Operaciones sueltas que usa el agente conversacional y Azure AI Foundry."},
    ],
)


@app.exception_handler(Exception)
def _error_legible(_request, exc: Exception):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={
        "detail": f"{type(exc).__name__}: {str(exc)[:500]}",
        "sugerencia": "Revisa GET /diagnostico y la consola donde corre el servidor."})


def check_key(x_api_key: str | None = Header(default=None, description="Solo si el servidor define TOOLS_API_KEY")):
    expected = os.getenv("TOOLS_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


# ------------------------------------------------------------------ modelos
class AnalyzeIn(BaseModel):
    topic: str = Field(..., description="Palabra clave o #hashtag", examples=["calidad del aire Bosa"])
    max_videos: int = Field(20, ge=1, le=100, description="Videos a analizar (1–100)")
    comments_per_video: int = Field(50, ge=0, le=300, description="Comentarios por video (0–300)")
    modo_prueba: bool = Field(False, description="true = datos sintéticos, sin costo. Útil para probar la instalación")
    confirmar_costo: bool = Field(
        False, description=f"Obligatorio en true si max_videos × comments_per_video supera {MAX_SIN_CONFIRMAR}")


class SearchIn(BaseModel):
    topic: str = Field(..., examples=["#bogota"])
    max_videos: int = Field(10, ge=1, le=50)


class CommentsIn(BaseModel):
    video_urls: list[str] = Field(..., examples=[["https://www.tiktok.com/@usuario/video/123"]])
    comments_per_video: int = Field(50, ge=1, le=300)
    topic: str = ""


# ------------------------------------------------------------------ utilidades
def _reports_root() -> Path:
    return Path(settings.output_dir).resolve()


def _report_dir(report_id: str) -> Path:
    if not _ID_RE.match(report_id):
        raise HTTPException(status_code=400, detail="report_id inválido")
    d = _reports_root() / report_id
    if not (d / "report.json").exists():
        raise HTTPException(status_code=404, detail=f"No existe el reporte '{report_id}'")
    return d


def _links(report_id: str) -> dict:
    base = f"/reportes/{report_id}"
    return {"ver": f"{base}/ver", "json": base,
            **{f"descargar_{n.replace('.', '_')}": f"{base}/descargar/{n}" for n in ARCHIVOS}}


def _cost_note(videos: int, per_video: int) -> str:
    total = f"{videos * per_video:,}".replace(",", ".")
    return (f"{videos} videos × {per_video} comentarios = hasta {total} comentarios. "
            "Costo aproximado: USD 0,5–5 por cada 1.000 comentarios (Apify) más centavos de LLM.")


def _page(title: str, body_html: str, banner: str = "") -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--bg:#fafaf9;--fg:#1c1917;--muted:#57534e;--line:#e7e5e4;--card:#fff;--accent:#0f766e;--warn:#fef3c7;--warnfg:#78350f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--line:#44403c;--card:#292524;--accent:#5eead4;--warn:#422006;--warnfg:#fde68a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 64px}}
nav{{font-size:14px;margin-bottom:16px}} nav a{{margin-right:14px}}
a{{color:var(--accent)}} h1{{font-size:28px;line-height:1.25}} h2{{margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;display:block;overflow-x:auto}}
th,td{{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}} th{{background:var(--card)}}
code,pre{{background:var(--card);border:1px solid var(--line);border-radius:6px}} code{{padding:1px 4px}} pre{{padding:12px;overflow-x:auto}}
.banner{{background:var(--warn);color:var(--warnfg);padding:10px 14px;border-radius:8px;margin-bottom:16px}}
.mermaid{{background:#fff;border-radius:8px;padding:12px;margin:12px 0;overflow-x:auto}}
</style></head><body><main>
<nav><a href="/docs">← Swagger</a><a href="/reportes/ver">Reportes</a><a href="/guia">Guía</a><a href="/como-funciona">Cómo funciona</a></nav>
{banner}{body_html}
</main>
<script type="module">
const blocks=document.querySelectorAll('pre code.language-mermaid');
if(blocks.length){{
  const {{default:mermaid}}=await import('https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs');
  blocks.forEach(c=>{{const d=document.createElement('div');d.className='mermaid';d.textContent=c.textContent;c.parentElement.replaceWith(d);}});
  mermaid.initialize({{startOnLoad:false,theme:'neutral'}}); await mermaid.run();
}}
</script></body></html>"""


def _md_to_html(text: str, trusted: bool) -> str:
    import markdown
    # Los reportes incluyen texto de comentaristas: se escapa el HTML crudo antes de renderizar.
    src = text if trusted else html.escape(text, quote=False)
    return markdown.markdown(src, extensions=["tables", "fenced_code", "sane_lists"])


# ------------------------------------------------------------------ 1. Inicio
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["1. Inicio"], summary="¿El servicio está arriba?")
def health():
    return {"ok": True, "modo_por_defecto": "mock" if settings.mock else "live"}


@app.get("/diagnostico", tags=["1. Inicio"], summary="Verifica Python, paquetes, Apify y LLM (no muestra secretos)")
def diagnostico():
    from .doctor import run_checks
    checks = run_checks()
    return {"todo_listo": all(c["estado"] != "error" for c in checks), "chequeos": checks}


# ------------------------------------------------------------------ 2. Análisis
@app.post("/analyze", operation_id="analyze_tiktok_topic", dependencies=[Depends(check_key)], tags=["2. Análisis"],
          summary="Análisis completo de un tema (videos, comentarios, sentimiento, perfiles, informe)",
          description="Tarda 1–5 minutos en modo real. Devuelve las cifras clave, el informe en prosa y "
                      "`enlaces` para ver el reporte en el navegador o descargar los CSV.")
def analyze(body: AnalyzeIn):
    total = body.max_videos * body.comments_per_video
    if not body.modo_prueba and total > MAX_SIN_CONFIRMAR and not body.confirmar_costo:
        raise HTTPException(status_code=400, detail=(
            f"Corrida grande: {_cost_note(body.max_videos, body.comments_per_video)} "
            "Si estás de acuerdo, repite la petición con confirmar_costo: true."))
    args = dict(topic=body.topic, max_videos=body.max_videos, comments_per_video=body.comments_per_video)
    if body.modo_prueba == settings.mock:
        result = tools.analyze_tiktok_topic(**args)
    else:
        with _mock_lock:
            previous, settings.mock = settings.mock, body.modo_prueba
            try:
                result = tools.analyze_tiktok_topic(**args)
            finally:
                settings.mock = previous
    report_id = Path(result["output_dir"]).name if result.get("output_dir") else None
    return {"report_id": report_id, "enlaces": _links(report_id) if report_id else {}, **result}


# ------------------------------------------------------------------ 3. Reportes
def _list_reports() -> list[dict]:
    root = _reports_root()
    rows = []
    for d in sorted(root.glob("*/report.json"), reverse=True):
        try:
            s = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        g = s.get("sentimiento", {}).get("global", {})
        v = s.get("volumen", {})
        rows.append({"report_id": d.parent.name, "tema": s.get("topic"), "modo": s.get("mode"),
                     "fecha": s.get("generated_at"), "videos": v.get("videos"),
                     "comentarios_analizados": v.get("comentarios_analizados_sin_spam"),
                     "nss": g.get("nss"), "enlaces": _links(d.parent.name)})
    return rows


@app.get("/reportes", tags=["3. Reportes"], summary="Lista los reportes generados (más recientes primero)")
def reportes():
    return _list_reports()


@app.get("/reportes/ver", tags=["3. Reportes"], response_class=HTMLResponse,
         summary="Lista de reportes como página web (ábrela en el navegador)")
def reportes_html():
    rows = _list_reports()
    trs = "".join(
        f"<tr><td>{html.escape(r['fecha'] or '')}</td><td><a href=\"{r['enlaces']['ver']}\">{html.escape(r['tema'] or '')}</a></td>"
        f"<td>{'🧪 mock' if r['modo'] == 'mock' else 'real'}</td><td>{r['videos']}</td><td>{r['comentarios_analizados']}</td>"
        f"<td>{r['nss']}</td></tr>" for r in rows)
    body = ("<h1>Reportes de TikTok Pulse</h1>"
            + ("<table><tr><th>Fecha</th><th>Tema</th><th>Modo</th><th>Videos</th><th>Comentarios</th><th>NSS</th></tr>"
               + trs + "</table>" if rows else "<p>Aún no hay reportes. Corre <code>POST /analyze</code> desde el Swagger.</p>"))
    return _page("Reportes", body)


@app.get("/reportes/{report_id}", tags=["3. Reportes"], summary="Reporte en JSON (cifras clave + informe)")
def reporte(report_id: str):
    from .analysis import compact
    s = json.loads((_report_dir(report_id) / "report.json").read_text(encoding="utf-8"))
    return {"report_id": report_id, "enlaces": _links(report_id), **compact(s)}


@app.get("/reportes/{report_id}/ver", tags=["3. Reportes"], response_class=HTMLResponse,
         summary="Reporte completo como página web: tablero, informe y anexos")
def reporte_html(report_id: str):
    d = _report_dir(report_id)
    s = json.loads((d / "report.json").read_text(encoding="utf-8"))
    banner = ('<div class="banner">🧪 <b>Modo mock:</b> datos sintéticos de prueba, no son hallazgos reales.</div>'
              if s.get("mode") == "mock" else "")
    dl = " · ".join(f'<a href="/reportes/{report_id}/descargar/{n}">{n}</a>' for n in ARCHIVOS if (d / n).exists())
    body = _md_to_html((d / "report.md").read_text(encoding="utf-8"), trusted=False) + f"<h2>Archivos</h2><p>{dl}</p>"
    return _page(f"TikTok · {s.get('topic')}", body, banner)


@app.get("/reportes/{report_id}/descargar/{archivo}", tags=["3. Reportes"],
         summary="Descarga report.md, report.json, videos.csv o comments.csv")
def descargar(report_id: str, archivo: str):
    if archivo not in ARCHIVOS:
        raise HTTPException(status_code=400, detail=f"Archivo no permitido. Opciones: {', '.join(ARCHIVOS)}")
    f = _report_dir(report_id) / archivo
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"El reporte no tiene {archivo}")
    return FileResponse(f, media_type=ARCHIVOS[archivo], filename=f"{report_id}_{archivo}")


# ------------------------------------------------------------------ 4. Herramientas del agente
@app.post("/search", operation_id="search_tiktok_videos", dependencies=[Depends(check_key)],
          tags=["4. Herramientas del agente"], summary="Lista videos de un tema con URLs y métricas (sin comentarios)")
def search(body: SearchIn):
    return tools.search_tiktok_videos(**body.model_dump())


@app.post("/comments", operation_id="get_tiktok_comments", dependencies=[Depends(check_key)],
          tags=["4. Herramientas del agente"], summary="Comentarios con sentimiento de URLs concretas")
def comments(body: CommentsIn):
    return tools.get_tiktok_comments(**body.model_dump())


# ------------------------------------------------------------------ documentación
def _doc_page(name: str, title: str) -> str:
    f = DOCS_DIR / name
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"Falta docs/{name}")
    return _page(title, _md_to_html(f.read_text(encoding="utf-8"), trusted=True))


@app.get("/guia", include_in_schema=False, response_class=HTMLResponse)
def guia():
    return _doc_page("GUIA_DE_USO.md", "Guía de uso")


@app.get("/como-funciona", include_in_schema=False, response_class=HTMLResponse)
def como_funciona():
    return _doc_page("COMO_FUNCIONA.md", "Cómo funciona")
