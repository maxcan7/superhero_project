#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
esbuild \
  "$ROOT/superhero_project/static/ts/article.ts" \
  "$ROOT/superhero_project/static/ts/preview.ts" \
  "$ROOT/superhero_project/static/ts/editor.ts" \
  --outdir="$ROOT/superhero_project/static/js/" \
  --target=es2020
