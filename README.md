# TikTok Pulse: agente de social listening en TikTok

Le das un tema (palabra clave o `#hashtag`) y te devuelve:

- **Videos**: URL, autor, caption, vistas, likes, comentarios, compartidos, guardados, hashtags y engagement rate.
- **Comentarios**: texto, likes, usuario y URL del video.
- **Sentimiento por comentario**: positivo, negativo, neutral o mixto, con score de -1 a 1, emoción y detección de sarcasmo.
- **Agregados**: distribución de sentimiento, **Net Sentiment Score** (simple y ponderado por likes), emociones, videos más positivos y más negativos, y comentarios más likeados de cada polo.
- **Lectura cualitativa (LLM)**: resumen, temas, elogios, quejas, preguntas frecuentes y alertas reputacionales.
- **Archivos**: `outputs/<fecha>_<tema>/` con `report.md`, `report.json`, `videos.csv` y `comments.csv`.

## Inicio rápido (sin programar)

| | Mac / Linux | Windows |
|---|---|---|
| 1. Instalar (una vez) | `./instalar.sh` | `powershell -ExecutionPolicy Bypass -File .\instalar.ps1` |
| 2. Poner llaves en `.env` | `APIFY_TOKEN`, `OPENAI_API_KEY` | igual |
| 3. Arrancar | `./iniciar.sh` | `powershell -ExecutionPolicy Bypass -File .\iniciar.ps1` |

Se abre el Swagger en http://localhost:8000/docs. Desde ahí corres `POST /analyze` y ves el reporte en `/reportes/{id}/ver`.

- **Guía de uso paso a paso:** [docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md) (también en http://localhost:8000/guia)
- **Cómo funciona, con diagramas:** [docs/COMO_FUNCIONA.md](docs/COMO_FUNCIONA.md) (también en http://localhost:8000/como-funciona)

## Qué entrega el informe

1. **Tablero**: videos, vistas, comentarios reportados frente a analizados, comentaristas únicos, spam, NSS simple y ponderado por likes, distribución con IC95 de Wilson y engagement.
2. **Informe en prosa de analista**: resumen ejecutivo · volumen y alcance · **quién publica** (tiers de creadores, tipo, ángulo, postura, concentración del alcance) · **quién comenta** (perfiles: usuarios con experiencia, potenciales compradores, escépticos, expertos, seguidores, humor y spam; recurrencia) · **qué se dice** (aspectos generados para el tema, con sentimiento y citas) · sentimiento y emociones · evolución temporal · riesgos y oportunidades · recomendaciones · notas metodológicas.
3. **Anexos**: tablas por aspecto, por perfil, por tier y de top creadores, más emociones y hashtags.

Para el informe conviene un modelo más capaz (`AZURE_OPENAI_ANALYST_DEPLOYMENT`, p. ej. gpt-4.1). La clasificación masiva va con gpt-4o-mini.

## Arquitectura

```
tiktok_source.py  ← proveedor de datos (Apify hoy; intercambiable)
sentiment.py      ← taxonomía de aspectos + clasificación de comentarios y videos (LLM, JSON)
stats.py          ← estadísticas (volumen, alcance, perfiles, tiers, aspectos, IC95, tiempo, concentración)
narrative.py      ← informe en prosa experto (LLM; plantilla en modo mock)
analysis.py       ← orquestación + reporte md/json/csv
tools.py          ← 3 tools con sus JSON schemas (las mismas se usan en Foundry)
agent.py          ← loop local de function calling (para iterar rápido)
api.py            ← FastAPI con las tools → /openapi.json para Foundry
```

### ¿Por qué Apify y no la API oficial de TikTok?

- **Research API**: solo es para academia sin ánimo de lucro en EE. UU., Europa, Reino Unido y Suiza, con aprobación manual. **No aplica a uso comercial ni a Colombia.**
- **Display API / Login Kit**: solo da acceso al contenido de la cuenta que autoriza, no permite buscar por tema.
- **Apify** (`clockworks/tiktok-scraper` y `clockworks/tiktok-comments-scraper`): se paga por resultado y el plan gratuito trae USD 5 al mes. Para cambiar de proveedor (EnsembleData, TikAPI, etc.) basta con implementar `search_videos` y `get_comments` en una clase nueva.

> ⚠️ El scraping de datos públicos está en zona gris frente a los Términos de Servicio de TikTok. Para uso con clientes conviene revisarlo con el equipo legal, no guardar datos personales innecesarios y anonimizar a los usuarios en los reportes.

## Correr el MVP

```bash
cd tiktok-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # y llenar las llaves

# 1) Probar sin llaves (datos sintéticos)
python run.py analyze "creatina" --mock

# 2) Real: solo pipeline
python run.py analyze "creatina" --videos 20 --comments 50
python run.py analyze "#skincarecolombia" --videos 30

# 3) Real: agente conversacional
python run.py chat
#   > ¿qué se dice de la reforma pensional en TikTok?
#   > dame solo las URLs de los 10 videos más vistos de #bogota
#   > analiza los comentarios de https://www.tiktok.com/@x/video/123

# 4) API de tools (para Foundry)
uvicorn tiktok_agent.api:app --port 8000   # docs en http://localhost:8000/docs
```

**Costo de referencia** por análisis de 20 videos × 50 comentarios (1.000 comentarios): Apify cobra unos centavos de dólar por los videos y entre USD 0,5 y 5 por los comentarios según la tarifa vigente del actor. Con gpt-4o-mini, el sentimiento cuesta menos de USD 0,01.

## Paso a Azure AI Foundry (fase 2)

1. **Modelo**: desplegar `gpt-4o-mini` (sentimiento) y `gpt-4o` o `gpt-4.1` (agente) en el proyecto de Foundry. El código ya usa `AZURE_OPENAI_*`.
2. **Hospedar las tools**: subir `api.py` a **Azure Container Apps** o a **Azure Functions**, con `TOOLS_API_KEY` y `APIFY_TOKEN` guardados en **Key Vault**.
3. **Crear el agente en Foundry Agent Service**:
   - Instrucciones: `SYSTEM_PROMPT` de `agent.py`.
   - Tool **OpenAPI**: importar `https://<app>/openapi.json`, con autenticación por API key (header `x-api-key`) o Managed Identity.
   - Alternativa: registrar `TOOL_SCHEMAS` como *function tools* desde el SDK.
4. **Extras útiles**:
   - Code Interpreter para gráficas sobre los CSV.
   - Persistencia en Blob o Cosmos DB para histórico y tendencias en el tiempo.
   - Un *scheduled run* diario para monitorear temas.
   - Evaluaciones en Foundry: calidad del sentimiento contra un set etiquetado a mano.
