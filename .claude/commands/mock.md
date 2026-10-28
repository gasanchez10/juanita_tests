---
description: Corre el pipeline completo con datos sintéticos (sin costo)
argument-hint: <tema o #hashtag>
allowed-tools: Bash, Read
---
Corre `.venv/bin/python run.py analyze "$ARGUMENTS" --mock` (si $ARGUMENTS está vacío usa "creatina").
Lee el `report.md` generado (ruta en la última línea de la salida) y muestra un resumen: tablero + primeras secciones del informe.
Aclara de forma explícita que son **datos sintéticos** y que sirven para validar el pipeline, no para sacar conclusiones.
