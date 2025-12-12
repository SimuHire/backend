#!/usr/bin/env bash
set -euo pipefail

echo "🔍 Running pre-commit checks..."

# Directory of THIS script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# cd into backend dir (where pyproject.toml actually is)
cd "$SCRIPT_DIR"

if ! command -v poetry >/dev/null 2>&1; then
  echo "❌ Poetry is not installed or not on PATH."
  echo "   Install it with: pip install poetry"
  exit 1
fi

echo "➡️  Linting backend with Ruff (autofix)..."
poetry run ruff check . --fix

echo "➡️  Formatting backend with Ruff..."
poetry run ruff format .

echo "➡️  Running backend tests..."
poetry run pytest --maxfail=1

echo "✅ All pre-commit checks passed!"
exit 0
