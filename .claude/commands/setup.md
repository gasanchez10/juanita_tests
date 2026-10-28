---
description: Instala el entorno de TikTok Pulse y valida llaves/conexiones
allowed-tools: Bash, Read
---
Prepara el entorno de TikTok Pulse siguiendo la sección "Setup" de CLAUDE.md:

1. Si no existe `.venv/`, créalo con `python3 -m venv .venv`.
2. `.venv/bin/pip install -r requirements.txt`
3. Si no existe `.env`, cópialo desde `.env.example` (`cp -n .env.example .env`). NO lo leas ni lo edites: dile al usuario qué variables debe llenar y dónde conseguir cada llave (tabla de CLAUDE.md).
4. Corre `.venv/bin/python run.py doctor`.
5. Corre `.venv/bin/python run.py analyze "creatina" --videos 5 --comments 10 --mock` como prueba de humo.

Resume en una tabla corta qué quedó ✅ y qué ❌, y para cada ❌ la acción concreta que debe hacer el usuario.
