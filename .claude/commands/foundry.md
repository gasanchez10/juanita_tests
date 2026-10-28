---
description: Guía/plan para llevar TikTok Pulse a Azure AI Foundry Agent Service
allowed-tools: Bash, Read, WebSearch, WebFetch
---
Lee la sección "Roadmap: paso a Azure AI Foundry" de CLAUDE.md y el código de `tiktok_agent/api.py`, `tools.py` y `agent.py`.

Antes de proponer código de SDK, **busca la documentación vigente** de Azure AI Foundry Agent Service (OpenAPI tools, function tools, `azure-ai-projects`) porque la API cambia entre versiones.

Entrega un plan paso a paso, concreto para este repo: Dockerfile para `api.py`, despliegue en Azure Container Apps (comandos `az`), secretos en Key Vault, registro de la OpenAPI tool y creación del agente con `SYSTEM_PROMPT`, más cómo probarlo. Pregunta antes de crear recursos en Azure o de ejecutar comandos `az` que cuesten dinero.
