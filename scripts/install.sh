#!/usr/bin/env bash
# Installe l'environnement Python figé (uv.lock) dans .venv. Aucune dépendance système.
# Usage : scripts/install.sh   (depuis n'importe où)
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null; then
  echo "uv absent : installation (https://docs.astral.sh/uv/)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv sync --frozen

.venv/bin/python -c "import pdfplumber; print('pdfplumber', pdfplumber.__version__)"
echo "OK. Lancer les tests : .venv/bin/pytest -q"
