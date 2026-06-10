#!/usr/bin/env bash
set -euo pipefail

if [ "$(uname)" = "Linux" ]; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y pandoc tree
  else
    echo "Run as root to install: apt-get update && apt-get install -y pandoc tree"
  fi
else
  echo "Please install 'pandoc' and 'tree' for your platform (e.g. 'brew install pandoc tree' on macOS)."
fi
