---
description: Sentimiento y análisis de los comentarios de una o varias URLs de TikTok
argument-hint: <url1> [url2 ...] [tema]
allowed-tools: Bash, Read
---
Argumentos: `$ARGUMENTS`. Separa las URLs (las que empiezan por http) del resto del texto, que es el tema de referencia (opcional).

Corre `.venv/bin/python run.py comments <urls…> --comments 100 --topic "<tema>"` con timeout de 600000 ms.

Con el JSON resultante, responde como analista: N comentarios, distribución de sentimiento y NSS, de qué aspectos se habla, qué perfiles comentan y 3 a 5 citas representativas (positivas y negativas) con sus likes, más una conclusión de 2 o 3 frases. No listes @usuarios de comentaristas.
