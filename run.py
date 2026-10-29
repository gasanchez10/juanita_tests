"""CLI de TikTok Pulse.

  python run.py analyze "tema o #hashtag" [--videos 20] [--comments 50] [--mock]
  python run.py comments URL [URL ...] [--comments 50] [--topic "tema"] [--mock]
  python run.py chat [--mock]
  python run.py doctor
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def doctor() -> int:
    """Verifica entorno, llaves y conectividad sin imprimir secretos."""
    from tiktok_agent.doctor import run_checks

    checks = run_checks()
    for c in checks:
        print({"ok": "✅", "aviso": "⚠️ ", "error": "❌"}[c["estado"]], c["mensaje"])
    ok = all(c["estado"] != "error" for c in checks)
    print("\nTodo listo ✅" if ok else "\nHay problemas ❌ (ver arriba)")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description="TikTok Pulse — social listening en TikTok")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="Análisis completo de un tema")
    a.add_argument("topic")
    a.add_argument("--videos", type=int, default=20)
    a.add_argument("--comments", type=int, default=50)
    a.add_argument("--orden-videos", choices=["relevancia", "mas_likeados", "mas_recientes"], default="relevancia")
    a.add_argument("--orden-comentarios", choices=["relevancia", "mas_likeados", "mas_recientes"], default="relevancia")
    a.add_argument("--contexto", default="", help="Qué significa el tema y qué excluir")
    a.add_argument("--mock", action="store_true")
    c = sub.add_parser("comments", help="Comentarios + sentimiento de URLs concretas (JSON)")
    c.add_argument("urls", nargs="+")
    c.add_argument("--comments", type=int, default=50)
    c.add_argument("--topic", default="")
    c.add_argument("--mock", action="store_true")
    ch = sub.add_parser("chat", help="Agente conversacional interactivo")
    ch.add_argument("--mock", action="store_true")
    sub.add_parser("doctor", help="Verifica llaves y conectividad")
    args = p.parse_args()

    if getattr(args, "mock", False):
        os.environ["MOCK_MODE"] = "true"

    # imports después de fijar MOCK_MODE
    if args.cmd == "doctor":
        return doctor()

    if args.cmd == "analyze":
        from tiktok_agent.analysis import analyze_topic, render_markdown
        m = analyze_topic(args.topic, args.videos, args.comments, orden_videos=args.orden_videos,
                          orden_comentarios=args.orden_comentarios, contexto=args.contexto)
        print(render_markdown(m))
        print(f"\n📁 Reporte guardado en: {m['output_dir']}")
        return 0

    if args.cmd == "comments":
        from tiktok_agent.tools import get_tiktok_comments
        print(json.dumps(get_tiktok_comments(args.urls, args.comments, args.topic), ensure_ascii=False, indent=2, default=str))
        return 0

    from tiktok_agent.agent import TikTokAgent
    agent = TikTokAgent()
    print("TikTok Pulse 🤖  (escribe 'salir' para terminar)")
    while True:
        try:
            q = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"salir", "exit", "quit"}:
            break
        if q:
            print("\nAgente:", agent.ask(q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
