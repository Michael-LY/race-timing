#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="${APP_NAME:-race-timing}"
OUTPUT="$DIST_DIR/${APP_NAME}-release.tar.gz"

mkdir -p "$DIST_DIR"
rm -f "$OUTPUT"

tar -czf "$OUTPUT" \
  --exclude='.git' \
  --exclude='.github' \
  --exclude='dist' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.mypy_cache' \
  --exclude='instance/*.db' \
  -C "$ROOT_DIR" .

echo "Created release archive: $OUTPUT"
