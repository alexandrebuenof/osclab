#!/usr/bin/env bash
# OscLab — atalho para Linux/macOS/WSL.
#
# Repassa os argumentos para o app.py. Sem argumentos, sobe a interface web.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$HERE/app.py" ]; then
  echo "[ERRO] Nao encontrei app.py em $HERE — copia incompleta." >&2
  exit 1
fi

# OSCLAB_ROOT e' a versao em execucao; OSCLAB_DATA_DIR sao os dados do usuario.
# Hoje sao a mesma pasta; numa instalacao versionada deixam de ser.
export OSCLAB_ROOT="$HERE"
export OSCLAB_DATA_DIR="$HERE"

PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

exec "$PY" "$HERE/app.py" "$@"
