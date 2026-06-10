#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

if ! command -v pandoc >/dev/null 2>&1; then
  echo "Warning: pandoc not found. Install pandoc (apt/brew/choco) or let pypandoc download it."
fi

echo "Running docs conversion..."
python docs_converter/godot_docs_converter.py

echo "Generating docs tree..."
if command -v tree >/dev/null 2>&1; then
  tree docs/. > docs/docs_tree.txt
else
  python - <<'PY'
import os
def tree(path, prefix=''):
    entries = sorted(os.listdir(path))
    for i, name in enumerate(entries):
        full = os.path.join(path, name)
        connector = '└── ' if i == len(entries)-1 else '├── '
        print(prefix + connector + name)
        if os.path.isdir(full):
            extension = '    ' if i == len(entries)-1 else '│   '
            tree(full, prefix + extension)
print('docs/')
tree('docs')
PY
fi

echo "Starting MCP server..."
python main.py
