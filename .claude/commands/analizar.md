---
description: Análisis real de social listening en TikTok sobre un tema (videos, comentarios, sentimiento, quién opina y qué opina)
argument-hint: <tema o #hashtag> [videos=20] [comentarios=50]
allowed-tools: Bash, Read
---
Argumentos: `$ARGUMENTS`
Interprétalos así: si los dos últimos tokens son números, son `videos` y `comentarios` por video. Si solo el último es número, son `videos`. Todo lo demás es el tema. Valores por defecto: 20 videos, 50 comentarios.

Sigue el "Flujo de trabajo como analista" de CLAUDE.md:

1. Si es la primera corrida de esta sesión, corre `.venv/bin/python run.py doctor`. Si hay ❌, detente y explica cómo resolverlo.
2. Si videos × comentarios > 3000, muestra el costo estimado (tabla de CLAUDE.md) y pide confirmación antes de correr.
3. Corre `.venv/bin/python run.py analyze "<tema>" --videos <videos> --comments <comentarios>` con timeout de Bash de 600000 ms.
4. Lee el `report.md` completo de la ruta que imprime la última línea. Verifica en `report.json` que `mode` sea `live`.
5. Revisa la calidad de los datos: si `videos.csv` tiene vistas o seguidores en 0 en todos los videos, o hay 0 comentarios, avísalo y diagnostica con la tabla de troubleshooting antes de presentar conclusiones.
6. Responde en este orden: línea de muestra (modo, N videos, N comentarios, N comentaristas, fecha) → tablero en tabla → **informe en prosa completo** (campo `informe`) → ruta del reporte → 2 o 3 profundizaciones sugeridas.

No inventes cifras ni citas. No listes @usuarios de comentaristas; los creadores sí se pueden nombrar.
