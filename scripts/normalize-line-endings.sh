#!/usr/bin/env bash
set -euo pipefail

# Normalize line endings to LF for repo scripts and SQL files.
# Uses dos2unix if available, otherwise falls back to awk to strip CR.

FILES=(
  "src/init-multiple-dbs.sh"
  "scripts/*.sh"
  "producer/*.py"
  "src/**/*.py"
  "*.sh"
  "*.ps1"
)

echo "Normalizing line endings (LF)..."
if command -v dos2unix >/dev/null 2>&1; then
  for f in "${FILES[@]}"; do
    for file in $(ls $f 2>/dev/null || true); do
      echo "dos2unix $file"
      dos2unix "$file" || true
    done
  done
else
  echo "dos2unix not found; stripping CR with awk..."
  for f in "${FILES[@]}"; do
    for file in $(ls $f 2>/dev/null || true); do
      echo "fixing $file"
      awk '{ sub(/\r$/, ""); print }' "$file" > "$file.fixed" && mv "$file.fixed" "$file"
    done
  done
fi

echo "Done."
