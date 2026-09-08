#!/usr/bin/env bash
set -euo pipefail

python -m compileall -q api audio core llm meetly

if [[ -d sdk/typescript/node_modules ]]; then
  npm --prefix sdk/typescript run build
fi