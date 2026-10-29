# Estructura del JSON de TikTok Pulse

Este documento describe cada llave de los resultados: qué contiene, de qué tipo es y cómo se calcula. Los ejemplos salen de una corrida real ("inseguridad Bosa", 5 videos × 20 comentarios).

Para el uso general ve a la [Guía de uso](/guia); para el funcionamiento interno, a [Cómo funciona](/como-funciona).

---

## 1. Dónde aparece el JSON

| Dónde | Qué trae |
|---|---|
| `outputs/<id>/report.json` | **Todo**: todas las llaves de este documento |
| Respuesta de `POST /analyze` | Versión compacta: `report_id`, `enlaces` y las llaves marcadas con ✅ en la sección 2 |
| `GET /reportes/{report_id}` | La misma versión compacta, leída de un reporte guardado |
| `outputs/<id>/videos.csv` y `comments.csv` | Tablas planas, por video y por comentario (sección 4) |

El `report_id` es el nombre de la carpeta: `AAAAMMDD-HHMMSS_tema`, por ejemplo `20261028-190826_inseguridad-bosa`.

**Tipos:** `str` texto · `int` entero · `float` decimal · `bool` true/false · `list` lista · `dict` objeto · `null` sin dato.
**Porcentajes:** van de 0 a 100 con un decimal (`60.6` = 60,6%).
**Fechas:** ISO 8601 (`2026-10-28T19:08:08`).

---

## 2. Llaves de primer nivel

| Llave | Tipo | En `/analyze` | Contenido |
|---|---|:---:|---|
| `topic` | str | ✅ | El tema tal como se pidió |
| `mode` | str | ✅ | `live` = datos reales de TikTok · `mock` = datos sintéticos de prueba. **Nunca presentes un `mock` como hallazgo** |
| `generated_at` | str | ✅ | Fecha y hora en que terminó el análisis |
| `elapsed_s` | float | | Segundos que tardó la corrida |
| `output_dir` | str | ✅ | Carpeta donde quedaron los archivos |
| `parametros` | dict | ✅ | Lo que se pidió (sección 3.1) |
| `filtro_relevancia` | dict | ✅ | Cómo se interpretó el tema y qué videos se descartaron (3.2). En `/analyze`, `descartados` es solo el número |
| `costos` | dict | ✅ | Tokens y dinero gastados en esta corrida (3.3) |
| `saldo` | dict | ✅ | Crédito disponible y alertas de recarga (3.4) |
| `volumen` | dict | ✅ | Cuántos videos, comentarios y personas (3.5) |
| `alcance` | dict | ✅ | Vistas, likes, engagement y concentración (3.6) |
| `sentimiento` | dict | ✅ | Polaridad, NSS, IC95, emociones, postura (3.7) |
| `comentaristas_por_perfil` | list | ✅ | Quién comenta, por rol (3.8) |
| `creadores_por_tier` | list | ✅ | Quién publica, por tamaño de cuenta (3.9) |
| `top_creadores` | list | ✅ | Los 10 videos con más vistas y su creador (3.9). En `/analyze` solo los 6 primeros |
| `contenido` | dict | ✅ | Ángulos, posturas, tipos de creador, hashtags (3.10). En `/analyze` solo `angulos`, `postura_creadores` y `tipos_creador` |
| `aspect_taxonomy` | list[str] | ✅ | Los 5 a 9 subtemas que el LLM definió para este tema |
| `aspectos` | list | ✅ | Métricas y citas por subtema (3.11). En `/analyze` sin `pct`, `likes_totales`, `emocion_principal` ni `citas_neutras` |
| `temporal` | dict | | Fechas de videos y comentarios por día (3.12) |
| `concentracion` | dict | ✅ | Qué tan concentrada está la conversación (3.13) |
| `videos_mas_positivos` | list | | Hasta 3 videos con el NSS de audiencia más alto (3.14) |
| `videos_mas_negativos` | list | | Hasta 3 videos con el NSS de audiencia más bajo (3.14) |
| `top_comentarios_positivos` | list | | Los 5 comentarios positivos con más likes |
| `top_comentarios_negativos` | list | | Los 5 comentarios negativos con más likes |
| `top_preguntas` | list | ✅ | Los 5 comentarios con "?" con más likes: `{text, likes}` |
| `videos` | list | | Tabla completa por video (3.14) |
| `metodologia` | dict | | Textos fijos que explican fuente, clasificación, NSS, IC95 y limitaciones |
| `informe` | str | ✅ | Informe en prosa del analista, en Markdown |

Solo en la respuesta de `/analyze` y de `GET /reportes/{id}`:

| Llave | Tipo | Contenido |
|---|---|---|
| `report_id` | str | Identificador del reporte |
| `enlaces.ver` | str | Página web del reporte. Ábrela como `http://localhost:8000` + este valor |
| `enlaces.json` | str | Este mismo JSON compacto |
| `enlaces.descargar_report_md`, `descargar_report_json`, `descargar_videos_csv`, `descargar_comments_csv` | str | Descargas de cada archivo |

---

## 3. Detalle por bloque

### 3.1 `parametros`

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `topic` | str | `"inseguridad Bosa"` | Tema pedido. Si empieza con `#`, se buscó por hashtag |
| `contexto` | str | `""` | Aclaración opcional del usuario sobre qué significa el tema |
| `max_videos` | int | `5` | Videos pedidos |
| `comments_per_video` | int | `20` | Comentarios pedidos por video |
| `orden_videos` | str | `"relevancia"` | `relevancia` (ranking de TikTok), `mas_likeados` o `mas_recientes` |
| `orden_comentarios` | str | `"relevancia"` | Igual, para los comentarios de cada video |

### 3.2 `filtro_relevancia`

Antes de descargar comentarios, el LLM interpreta el tema, genera varias búsquedas y descarta los videos que no lo tratan. Así no se paga por comentarios de videos irrelevantes.

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `interpretacion` | str | `"…la delincuencia y la seguridad ciudadana en la localidad de Bosa…"` | Qué conversación se estudió. Si se dio `contexto`, manda el contexto |
| `consultas` | list[str] | `["inseguridad Bosa", "delincuencia Bosa", "robos en Bosa", "violencia en Bosa"]` | Búsquedas enviadas a TikTok. La primera es siempre la original; con `#hashtag` solo se busca el hashtag |
| `incluir` | list[str] | `["testimonios de robos", …]` | Criterios de lo que sí cuenta como tema |
| `excluir` | list[str] | `["inseguridad emocional", …]` | Sentidos o contenidos que no cuentan |
| `videos_encontrados` | int | `10` | Videos que devolvió la búsqueda (se pide el doble de `max_videos`) |
| `videos_relevantes` | int | `7` | Los que pasaron el filtro |
| `videos_usados` | int | `5` | Los analizados: los relevantes, ordenados según `orden_videos` y cortados en `max_videos` |
| `descartados` | list | | Por cada video descartado: `autor`, `url`, `caption` (primeros 120 caracteres) y `motivo` |

### 3.3 `costos`

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `llm.por_modelo.<modelo>.llamadas` | int | `5` | Llamadas a ese modelo en la corrida |
| `llm.por_modelo.<modelo>.tokens_entrada` | int | `7215` | Tokens enviados (prompt) |
| `llm.por_modelo.<modelo>.tokens_salida` | int | `4326` | Tokens generados (respuesta) |
| `llm.por_modelo.<modelo>.tokens_total` | int | `11541` | Suma de ambos |
| `llm.por_modelo.<modelo>.costo_usd_estimado` | float/null | `0.0037` | Tokens × precio público del modelo. `null` si el modelo no está en la tabla de precios |
| `llm.tokens_entrada`, `tokens_salida`, `tokens_total` | int | `20115` | Totales de todos los modelos |
| `llm.costo_usd_estimado` | float | `0.0344` | Costo LLM total estimado |
| `llm.precio_desconocido` | list[str] | `[]` | Modelos sin precio en la tabla (su costo no se suma) |
| `apify.corridas[].actor` | str | `"clockworks/tiktok-scraper"` | Actor de Apify ejecutado |
| `apify.corridas[].run_id` | str | | ID de la ejecución, para buscarla en console.apify.com → Runs |
| `apify.corridas[].eventos_cobrados` | dict | `{"result": 9, "actor-start": 1}` | Eventos que Apify cobró (resultados, inicios, add-ons de orden) |
| `apify.corridas[].costo_usd` | float | `0.0343` | Eventos × tarifa vigente del actor para el plan de la cuenta |
| `apify.costo_usd` | float | `0.1243` | Costo Apify total |
| `total_usd_estimado` | float | `0.1587` | LLM + Apify |

Los precios del LLM son los públicos de OpenAI y están en `tiktok_agent/costos.py` (`LLM_PRICES_PER_M`). Si cambian o usas Azure con otra tarifa, ajústalos ahí. En modo `mock` todo es 0.

### 3.4 `saldo`

Se consulta al final de cada corrida real. También está disponible en cualquier momento con `GET /saldo`.

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `apify.plan` | str | `"FREE"` | Plan de la cuenta de Apify |
| `apify.uso_mes_usd` | float | `1.27` | Gastado en el ciclo mensual actual |
| `apify.limite_mes_usd` | float | `5.0` | Límite del ciclo (en FREE, el crédito incluido) |
| `apify.disponible_usd` | float | `3.73` | Límite − uso |
| `apify.ciclo_termina` | str | `"2026-11-19T23:59:59Z"` | Cuándo se renueva el crédito |
| `apify.costo_analisis_estandar_usd` | float | `1.4` | Costo máximo de un análisis de 20 × 50 con las tarifas vigentes |
| `apify.analisis_estandar_restantes` | int | `2` | Cuántos análisis estándar alcanzan con el saldo |
| `openai.disponible_usd` | null | `null` | OpenAI no expone el saldo prepago con una API key normal |
| `openai.nota` | str | | Dónde revisarlo a mano |
| `necesita_recarga` | bool | `false` | `true` si el saldo de Apify no alcanza para un análisis estándar |
| `alertas` | list[str] | `[]` | Mensajes de recarga, con el enlace a facturación |

Si `apify` trae `{"error": …}`, no se pudo consultar el saldo. Además, `POST /analyze` rechaza con código **402** una corrida cuyo costo máximo supere el saldo disponible.

### 3.5 `volumen`

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `videos` | int | `5` | Videos analizados |
| `creadores_unicos` | int | `5` | Cuentas distintas que publicaron esos videos |
| `comentarios_reportados_en_videos` | int | `719` | Comentarios que TikTok dice que tienen esos videos |
| `comentarios_extraidos` | int | `71` | Comentarios descargados |
| `comentarios_analizados_sin_spam` | int | `71` | Extraídos menos spam: la base de todas las métricas de opinión |
| `spam_detectado` | int | `0` | Comentarios marcados como spam o bots |
| `spam_pct` | float | `0.0` | % de spam sobre los extraídos |
| `cobertura_muestra_pct` | float | `9.9` | Extraídos ÷ reportados. Suele ser baja: se leen los comentarios más visibles |
| `comentaristas_unicos` | int | `70` | Personas distintas que comentaron |
| `comentarios_por_comentarista` | float | `1.01` | Promedio de comentarios por persona |
| `comentaristas_recurrentes` | int | `1` | Personas con más de un comentario |
| `pct_comentarios_de_recurrentes` | float | `2.8` | % del volumen que aportan los recurrentes |
| `likes_en_comentarios` | int | `8625` | Suma de likes de los comentarios analizados |
| `respuestas_en_comentarios` | int | `108` | Suma de respuestas que reciben (no se descargan) |

### 3.6 `alcance`

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `vistas`, `likes`, `compartidos`, `guardados` | int | `1819985` | Sumas sobre los videos analizados |
| `vistas_mediana_por_video` | int | `31000` | Vistas del video típico |
| `engagement_rate_mediano_pct` | float | `1.33` | Mediana de (likes + comentarios + compartidos + guardados) ÷ vistas |
| `engagement_rate_promedio_pct` | float | `1.66` | Promedio del mismo cálculo |
| `concentracion_vistas_top1_pct` | float | `82.4` | % de vistas del video más visto |
| `concentracion_vistas_top3_pct` | float | `98.5` | % de vistas de los 3 más vistos. Alto = el tema es la reacción a pocos videos |
| `videos_publicidad` | int | `0` | Videos marcados como anuncio por TikTok |

### 3.7 `sentimiento`

El sentimiento tiene **tres clases**: `positivo`, `negativo` y `neutral`. Si un comentario mezcla elogio y crítica, el LLM elige la polaridad que domina; si ninguna domina, queda neutral.

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `global.n` | int | `71` | Comentarios analizados (sin spam) |
| `global.pct.positivo` / `negativo` / `neutral` | float | `19.7` / `60.6` / `19.7` | Distribución, suma 100 |
| `global.counts.positivo` / `negativo` / `neutral` | int | `14` / `43` / `14` | Conteos |
| `global.nss` | float | `-40.9` | **Net Sentiment Score** = % positivo − % negativo. Escala de −100 a 100: ≥30 claramente positivo · 10 a 30 moderadamente positivo · −10 a 10 equilibrado · −30 a −10 moderadamente negativo · ≤−30 claramente negativo |
| `global.ci95_positivo` | list[float, float] | `[12.1, 30.4]` | Intervalo de confianza de Wilson al 95% del % positivo |
| `global.ci95_negativo` | list[float, float] | `[48.9, 71.1]` | Ídem para el % negativo. Si los dos intervalos se cruzan, no se puede afirmar qué polo domina. El NSS no tiene intervalo propio |
| `global.avg_score` | float | `-0.352` | Promedio del score (−1 a 1) de cada comentario |
| `global.std_score` | float | `0.513` | Dispersión del score |
| `global.polarizacion_pct` | float | `59.2` | % de comentarios con score ≥ 0,6 o ≤ −0,6 (carga emocional fuerte) |
| `ponderado_por_likes.n` | int | `71` | Mismos comentarios |
| `ponderado_por_likes.pct` | dict | `{"positivo": 1.8, …}` | Distribución donde cada comentario pesa 1 + sus likes |
| `ponderado_por_likes.nss` | float | `-67.5` | NSS ponderado. Si es al menos 5 puntos menor que el simple, la audiencia **amplifica las críticas**; si es mayor, amplifica lo favorable |
| `emociones` | dict | `{"enojo": 27, "tristeza": 14, …}` | Conteo por emoción, de mayor a menor. Valores posibles: alegría, enojo, tristeza, miedo, sorpresa, asco, humor, curiosidad, confianza, ninguna |
| `sarcasmo_pct` | float | `15.5` | % de comentarios con sarcasmo |
| `postura.a_favor` / `en_contra` / `neutral` | float | `11.3` / `60.6` / `28.2` | Postura hacia el tema (no hacia el creador) |

### 3.8 `comentaristas_por_perfil[]`

Una fila por perfil presente, de mayor a menor. Los perfiles son **roles conversacionales** que el LLM deduce del texto, no datos demográficos.

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `perfil` | str | `"escéptico/crítico"` | Uno de: usuario con experiencia propia, potencial comprador/interesado, escéptico/crítico, experto/profesional, seguidor del creador, humor/entretenimiento, spam/bot, otro |
| `n` | int | `29` | Comentarios de ese perfil |
| `pct` | float | `40.8` | % sobre todos los comentarios extraídos (incluye spam) |
| `nss` | float | `-93.2` | NSS del perfil |
| `pct_positivo`, `pct_negativo` | float | `3.4`, `96.6` | Distribución del perfil |
| `likes_promedio` | float | `128.6` | Likes promedio de sus comentarios |

### 3.9 `creadores_por_tier[]` y `top_creadores[]`

Tiers por seguidores: `nano (<10k)`, `micro (10k–100k)`, `mid (100k–500k)`, `macro (500k–1M)`, `mega (>1M)`.

`creadores_por_tier[]`:

| Llave | Tipo | Contenido |
|---|---|---|
| `tier` | str | Tamaño de cuenta |
| `videos` | int | Videos de ese tier |
| `vistas` | int | Vistas sumadas |
| `pct_vistas` | float | % de las vistas totales |
| `nss_comentarios` | float/null | NSS de la audiencia en esos videos |

`top_creadores[]` (los 10 videos con más vistas):

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `autor` | str | `"redmasnoticias"` | Cuenta que publica (se puede nombrar) |
| `seguidores` | int | `3900000` | Seguidores de la cuenta |
| `tier` | str | `"mega (>1M)"` | Tamaño |
| `verificado` | bool | `true` | Cuenta verificada |
| `tipo` | str | `"medio de comunicación"` | Tipo de creador según el LLM (texto libre corto) |
| `angulo` | str | `"noticia"` | Ángulo del contenido (ver 3.10) |
| `postura_creador` | str | `"a_favor"` | Postura del creador hacia el tema |
| `vistas` | int | `1500000` | Vistas del video |
| `nss_comentarios` | float/null | `-5.0` | NSS de los comentarios de ese video |
| `url` | str | | Enlace al video |
| `caption` | str | | Primeros 140 caracteres del texto del video |

### 3.10 `contenido`

| Llave | Tipo | Contenido |
|---|---|---|
| `angulos` | dict | Videos por ángulo: educativo/informativo, testimonio/reseña, opinión, humor/entretenimiento, promoción/publicidad, noticia, polémica/debate, otro |
| `postura_creadores` | dict | Videos por postura del creador: a_favor, en_contra, neutral |
| `tipos_creador` | dict | Los 8 tipos de creador más frecuentes |
| `verificados` | int | Videos de cuentas verificadas |
| `hashtags` | list[[str, int]] | Los 15 hashtags más usados: `[["bogota", 3], …]` |
| `nss_audiencia_por_angulo` | dict | NSS de los comentarios según el ángulo del video |

### 3.11 `aspectos[]`

Una fila por subtema de `aspect_taxonomy`, más `otro` (comentarios que no tratan ningún subtema), de mayor a menor.

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `aspecto` | str | `"testimonios de robos"` | Subtema |
| `n` | int | `16` | Comentarios del subtema |
| `share_pct` | float | `22.5` | % de la conversación |
| `nss` | float | `-100.0` | NSS del subtema |
| `pct` | dict | | Distribución positivo / negativo / neutral |
| `likes_totales` | int | | Likes sumados |
| `emocion_principal` | str | `"tristeza"` | Emoción más frecuente |
| `citas_positivas`, `citas_negativas` | list | | Hasta 2 comentarios por polaridad, con más likes: `{text, likes, video_url}` |
| `citas_neutras` | list | | Hasta 1 comentario neutral |

### 3.12 `temporal`

| Llave | Tipo | Contenido |
|---|---|---|
| `rango_videos` | list[str, str] | Fecha del video más antiguo y del más reciente |
| `videos_por_fecha` | dict | Videos publicados por día |
| `comentarios_por_dia[]` | list | Últimos 45 días con actividad: `{fecha, comentarios, nss}` |
| `pico` | dict | El día con más comentarios: `{fecha, comentarios, nss}` |

### 3.13 `concentracion`

| Llave | Tipo | Ejemplo | Contenido |
|---|---|---|---|
| `pct_comentarios_video_top` | float | `28.2` | % de comentarios del video con más comentarios |
| `hhi` | float | `0.255` | Índice Herfindahl-Hirschman: suma de las participaciones al cuadrado de cada video. 1 = un solo video concentra todo |
| `lectura` | str | `"concentrada"` | > 0,25 concentrada · 0,10 a 0,25 moderada · < 0,10 distribuida |

### 3.14 `videos[]`, `videos_mas_positivos[]` y `videos_mas_negativos[]`

Las tres listas tienen las mismas llaves. `videos_mas_*` solo consideran videos con 5 o más comentarios analizados.

| Llave | Tipo | Contenido |
|---|---|---|
| `video_id`, `url` | str | Identificador y enlace |
| `caption` | str | Texto del video |
| `created_at` | str | Fecha de publicación |
| `author`, `author_nickname` | str | Cuenta y nombre visible |
| `author_followers` | int | Seguidores |
| `author_verified` | bool | Verificada |
| `author_bio` | str | Biografía de la cuenta |
| `views`, `likes`, `comments`, `shares`, `saves` | int | Métricas del video |
| `hashtags` | list[str] | Hashtags del video |
| `music` | str | Sonido usado |
| `is_ad` | bool | Marcado como anuncio |
| `location` | str | Ubicación o idioma que reporta TikTok |
| `relevante` | bool | Pasó el filtro de relevancia (siempre `true` en esta lista) |
| `motivo_relevancia` | str | Por qué el LLM lo consideró relevante |
| `angle` | str | Ángulo del contenido |
| `creator_stance` | str | Postura del creador hacia el tema |
| `creator_type` | str | Tipo de creador |
| `tier` | str | Tamaño de la cuenta |
| `engagement_rate` | float | (likes + comentarios + compartidos + guardados) ÷ vistas × 100 |
| `n_comentarios_analizados` | int | Comentarios analizados de este video (sin spam) |
| `nss` | float/null | NSS de su audiencia |
| `pct_positivo`, `pct_negativo` | float/null | Distribución de su audiencia |

---

## 4. Columnas de los CSV

Los CSV se abren directo en Excel (UTF-8 con BOM). Las listas van como texto JSON.

**`videos.csv`**: una fila por video analizado, con las mismas columnas de `videos[]` (3.14).

**`comments.csv`**: una fila por comentario extraído, spam incluido:

| Columna | Contenido |
|---|---|
| `comment_id` | Identificador |
| `video_url` | Video al que pertenece |
| `text` | Texto del comentario |
| `likes`, `replies` | Likes y respuestas que recibe |
| `created_at` | Fecha |
| `user` | Cuenta del comentarista. **Es un dato personal**: no lo publiques ni lo compartas fuera del equipo |
| `sentiment` | positivo, negativo o neutral |
| `score` | De −1 (muy negativo) a 1 (muy positivo) |
| `emotion` | Emoción principal |
| `sarcasm` | true si hay sarcasmo (el sentimiento ya es el real, no el literal) |
| `stance` | a_favor, en_contra o neutral respecto al tema |
| `aspect` | Subtema, u `otro` |
| `persona` | Rol del comentarista |
| `spam` | true si es spam (excluido de las métricas) |

---

## 5. Compatibilidad con reportes anteriores

Los reportes generados antes del 28 de octubre de 2026 no tienen `parametros`, `filtro_relevancia`, `costos` ni `saldo`, y pueden traer una cuarta clase de sentimiento, `mixto`, que ya no se usa.
