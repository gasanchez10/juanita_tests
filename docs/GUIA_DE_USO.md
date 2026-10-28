# Guía de uso de TikTok Pulse

Esta guía explica cómo instalar TikTok Pulse en tu computador, ponerlo a correr, analizar un tema y leer los resultados. No necesitas programar: todo se hace desde una página web llamada **Swagger**, que es un panel donde llenas un formulario y le das "Execute".

Si quieres entender qué hace el agente por dentro, lee [Cómo funciona](/como-funciona) (archivo `docs/COMO_FUNCIONA.md`).

---

## 1. Qué necesitas antes de empezar

| Requisito | Dónde se consigue |
|---|---|
| **Python 3.10 o superior** | [python.org/downloads](https://www.python.org/downloads/). En Windows, marca la casilla **"Add python.exe to PATH"** al instalar. |
| **La carpeta del proyecto** (`tiktok-agent`) | Te la comparten en un .zip. Descomprímela donde quieras, por ejemplo en el Escritorio. |
| **Llave de Apify** (`APIFY_TOKEN`) | [console.apify.com](https://console.apify.com) → Settings → API & Integrations. Es la que trae los videos y comentarios de TikTok. |
| **Llave de OpenAI** (`OPENAI_API_KEY`) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Es la que clasifica los comentarios y escribe el informe. Como alternativa sirve Azure OpenAI. |

> 🔐 **Las llaves son como contraseñas.** No las pegues en chats, correos ni documentos. Cada una va solo en el archivo `.env` de tu computador. Si alguien te comparte las suyas, que sea por un gestor de contraseñas.

Puedes hacer la instalación y la primera prueba **sin llaves**, con el modo prueba (datos sintéticos, sin costo).

---

## 2. Instalación (una sola vez)

### En Mac

1. Abre la app **Terminal**.
2. Escribe `cd ` (con un espacio al final), arrastra la carpeta `tiktok-agent` a la ventana de Terminal y presiona Enter.
3. Corre:
   ```bash
   ./instalar.sh
   ```

### En Windows

1. Abre la carpeta `tiktok-agent` en el Explorador de archivos.
2. Haz clic derecho en un espacio vacío → **Abrir en Terminal** (o "Abrir ventana de PowerShell aquí").
3. Corre:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
   ```

### Qué hace el instalador

- Verifica que tengas Python 3.10 o superior.
- Crea un entorno aislado (`.venv`) e instala las librerías necesarias. Tarda 1 o 2 minutos.
- Crea el archivo `.env` a partir de la plantilla `.env.example`, si no existe.
- Corre un **diagnóstico** y muestra ✅, ⚠️ o ❌ por cada componente.

### Poner las llaves

Abre el archivo `.env` con un editor de texto (TextEdit en Mac, Bloc de notas en Windows). Es un archivo oculto: en Mac presiona `Cmd + Shift + .` en Finder para verlo. Llena estas líneas y guarda:

```
APIFY_TOKEN=apify_api_...
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_ANALYST_MODEL=gpt-4.1
MOCK_MODE=false
```

- `OPENAI_MODEL` clasifica miles de comentarios, así que conviene que sea barato.
- `OPENAI_ANALYST_MODEL` escribe el informe final, así que conviene que sea bueno.
- Deja las líneas `AZURE_OPENAI_*` como están si no vas a usar Azure.

---

## 3. Arrancar el agente (cada vez que lo vayas a usar)

| Mac | Windows |
|---|---|
| `./iniciar.sh` | `powershell -ExecutionPolicy Bypass -File .\iniciar.ps1` |

Se abre el navegador en **http://localhost:8000/docs**, que es el Swagger. Deja la ventana de Terminal abierta mientras lo usas: ahí aparece el progreso de cada análisis. Para apagarlo, presiona `Ctrl + C` en esa ventana.

---

## 4. Usar el Swagger paso a paso

En el Swagger cada operación es una franja de color. Para usar una: clic en la franja → **Try it out** → llena los campos → **Execute**. La respuesta aparece abajo, en "Response body".

### Paso 1. Diagnóstico: `GET /diagnostico`

Execute sin llenar nada. Debe decir `"todo_listo": true`. Si algún chequeo sale con `"estado": "error"`, mira la sección 7 de esta guía.

### Paso 2. Prueba gratis: `POST /analyze` en modo prueba

En el cuerpo de la petición pega:

```json
{
  "topic": "creatina",
  "max_videos": 5,
  "comments_per_video": 20,
  "modo_prueba": true
}
```

Tarda unos segundos. Usa datos inventados, así que **no saques conclusiones de este resultado**: sirve para confirmar que todo funciona.

### Paso 3. Análisis real: `POST /analyze`

```json
{
  "topic": "calidad del aire Bosa",
  "max_videos": 20,
  "comments_per_video": 50,
  "modo_prueba": false
}
```

- **`topic`**: una palabra clave (`creatina`) o un hashtag (`#skincarecolombia`). Si empieza con `#`, busca por hashtag.
- **`max_videos`**: cuántos videos analizar (1 a 100).
- **`comments_per_video`**: cuántos comentarios por video (0 a 300).
- **`confirmar_costo`**: si pides más de 3.000 comentarios en total (por ejemplo 50 × 100), el agente se detiene, te muestra el costo estimado y te pide repetir la petición con `"confirmar_costo": true`.

⏱️ Un análisis real tarda **entre 1 y 5 minutos**. El Swagger mostrará "Loading" todo ese tiempo y en la Terminal verás el avance. No cierres la página.

### Paso 4. Ver el resultado organizado

La respuesta trae un bloque `enlaces`:

```json
"enlaces": {
  "ver": "/reportes/20261028-101909_creatina/ver",
  "descargar_comments_csv": "/reportes/20261028-101909_creatina/descargar/comments.csv",
  ...
}
```

Abre en el navegador **http://localhost:8000** seguido del enlace `ver`, por ejemplo `http://localhost:8000/reportes/20261028-101909_creatina/ver`. Verás el reporte completo como una página: tablero, informe en prosa y anexos.

Para ver todos los análisis hechos hasta ahora: **http://localhost:8000/reportes/ver**.

### Otras operaciones útiles

| Operación | Para qué |
|---|---|
| `GET /reportes` | Lista de reportes en JSON (tema, fecha, modo, NSS) |
| `GET /reportes/{report_id}` | Cifras clave e informe de un reporte, en JSON |
| `GET /reportes/{report_id}/descargar/{archivo}` | Descarga `report.md`, `report.json`, `videos.csv` o `comments.csv`. Los CSV abren bien en Excel |
| `POST /search` | Solo lista videos de un tema, sin comentarios. Es rápido y barato |
| `POST /comments` | Analiza los comentarios de URLs de TikTok concretas |

---

## 5. Cómo leer el reporte

**Primero, el modo.** Si arriba aparece la franja amarilla "🧪 Modo mock", los datos son sintéticos. Solo los reportes sin esa franja son datos reales de TikTok.

**Tablero**

| Métrica | Qué significa |
|---|---|
| **NSS** (Net Sentiment Score) | % positivos − % negativos, de −100 a 100. ≥30 claramente positivo · 10 a 30 moderadamente positivo · −10 a 10 equilibrado · −30 a −10 moderadamente negativo · ≤−30 claramente negativo |
| **NSS ponderado por likes** | El mismo cálculo, pero cada comentario pesa según sus likes. Si es más bajo que el NSS simple, la audiencia **amplifica las críticas**; si es más alto, amplifica lo favorable |
| **IC95** | Rango probable del % real. Si los rangos de positivo y negativo se cruzan, no se puede afirmar cuál domina |
| **Spam** | Comentarios de autopromoción o bots. Se excluyen de todas las métricas de opinión |
| **Engagement mediano** | (likes + comentarios + compartidos + guardados) ÷ vistas, en el video típico |

**Informe en prosa**: lo escribe el modelo analista a partir de las estadísticas. Cubre resumen, volumen, quién publica, quién comenta, qué se dice, sentimiento, evolución, riesgos, recomendaciones y notas metodológicas.

**Anexos**: tablas por aspecto (subtema), perfil de comentarista, tamaño de creador y top creadores.

**Antes de presentar resultados a un cliente, ten en cuenta:**

- La muestra **no es representativa** de la opinión pública: depende de qué videos muestre la búsqueda de TikTok.
- Con menos de 100 comentarios, toma cualquier porcentaje como indicio, no como conclusión.
- Si un video concentra la mayoría de las vistas o comentarios, el resultado es la reacción **a ese video**, no al tema en general.
- Verifica las cifras del informe contra el tablero. El modelo puede equivocarse al redactar.
- Los comentaristas son personas privadas: en presentaciones habla de perfiles, no de @usuarios. Los creadores sí se pueden nombrar.

---

## 6. Costos

| Uso | Ajustes | Comentarios | Costo aproximado |
|---|---|---:|---|
| Modo prueba | `modo_prueba: true` | sintéticos | USD 0 |
| Prueba de humo | 5 videos × 20 | 100 | < USD 0,10 |
| Análisis estándar | 20 × 50 | 1.000 | USD 0,5–5 |
| Profundo | 50 × 100 | 5.000 | USD 3–25 (pide confirmación) |

Casi todo el costo es de Apify, que cobra por resultado. El LLM cuesta centavos. Puedes ver el consumo en [console.apify.com](https://console.apify.com) → Billing y en [platform.openai.com/usage](https://platform.openai.com/usage).

---

## 7. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `python` no se reconoce / "Necesitas Python 3.10" | Instala Python desde python.org. En Windows marca "Add python.exe to PATH" y abre una Terminal nueva |
| Windows dice que la ejecución de scripts está deshabilitada | Usa el comando con `powershell -ExecutionPolicy Bypass -File ...` tal como aparece arriba |
| El navegador no abre o dice "no se puede conectar" | Verifica que la Terminal siga abierta con el servidor corriendo y entra a `http://localhost:8000/docs` |
| "Address already in use" | Ya hay otra copia corriendo. Ciérrala, o arranca en otro puerto: `PORT=8001 ./iniciar.sh` |
| Diagnóstico: `APIFY_TOKEN vacío o placeholder` | Falta la llave de Apify en `.env`, o sigue con el valor de ejemplo |
| Diagnóstico: `Apify rechazó el token` | La llave está mal copiada o fue revocada. Genera una nueva en Apify |
| Diagnóstico: `LLM no configurado` | Falta `OPENAI_API_KEY` en `.env` |
| Diagnóstico: `deployment 'X' falló` | El nombre del modelo en `OPENAI_MODEL` u `OPENAI_ANALYST_MODEL` no existe para tu cuenta, o no tienes saldo en OpenAI |
| El análisis devuelve `0 videos` | El tema no tiene resultados. Prueba un término más general o un `#hashtag` |
| Errores `429` o "lote fallido" en la Terminal | Límite de velocidad de OpenAI. Agrega `SENTIMENT_BATCH_SIZE=25` en `.env` y reinicia |
| Cambiaste `.env` y no pasa nada | Reinicia el servidor (`Ctrl + C` e `iniciar` otra vez). Las llaves se leen al arrancar |

Los reportes quedan guardados en la carpeta `outputs/` del proyecto, uno por análisis.
