"""Agente conversacional local (loop de function calling).
En Foundry este loop lo ejecuta Agent Service; aquí lo hacemos a mano para iterar rápido.
"""
from __future__ import annotations

import json

from .llm import analyst_model_name as model_name
from .llm import get_client
from .tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

SYSTEM_PROMPT = """Eres "TikTok Pulse", analista senior de social listening sobre TikTok para equipos en Latinoamérica.
Herramientas:
- analyze_tiktok_topic: análisis completo de un tema. Devuelve estadísticas y un campo `informe` (informe experto en prosa).
- search_tiktok_videos: solo listar videos/URLs. get_tiktok_comments: analizar URLs concretas.

Cuando el usuario pida analizar un tema:
1. Llama analyze_tiktok_topic (valores por defecto si no indica tamaño de muestra).
2. Responde con: (a) un tablero corto de estadísticas (tabla Markdown: videos, vistas, comentarios analizados,
   comentaristas únicos, NSS simple y ponderado, % pos/neg/neutral/mixto con IC95, spam), y
   (b) el campo `informe` COMPLETO, tal cual, sin resumirlo.
3. Cierra indicando dónde quedó el reporte (output_dir) y ofreciendo 2-3 profundizaciones concretas
   (p. ej. un aspecto, un creador, un perfil de comentarista).
En preguntas de seguimiento, responde con las cifras ya obtenidas antes de volver a llamar herramientas.
Responde en español. No inventes datos que no vengan de las herramientas. Recuerda que la muestra no es probabilística."""


class TikTokAgent:
    def __init__(self):
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.client = get_client()

    def ask(self, user_msg: str, max_steps: int = 6, verbose: bool = True) -> str:
        self.messages.append({"role": "user", "content": user_msg})
        for _ in range(max_steps):
            resp = self.client.chat.completions.create(
                model=model_name(), messages=self.messages, tools=TOOL_SCHEMAS, temperature=0.3,
            )
            msg = resp.choices[0].message
            self.messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return msg.content or ""
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                if verbose:
                    print(f"  ↳ {tc.function.name}({args})")
                try:
                    result = TOOL_FUNCTIONS[tc.function.name](**args)
                except Exception as e:  # el error vuelve al modelo para que se recupere
                    result = {"error": f"{type(e).__name__}: {e}"}
                self.messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:60_000],
                })
        return "Se alcanzó el máximo de pasos sin respuesta final."
