#!/usr/bin/env bash
# Generate TypeScript types from the FastAPI OpenAPI schema.
#
# Prerequisites:
#   npm install -g openapi-typescript
#
# Usage:
#   bash scripts/generate-types.sh              # from running server (default)
#   bash scripts/generate-types.sh offline      # without running server
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT="$ROOT_DIR/frontend/src/types/api-generated.d.ts"
OPENAPI_URL="${OPENAPI_URL:-http://localhost:8000/openapi.json}"

if ! command -v npx &>/dev/null; then
  echo "Error: npx not found. Install Node.js first." >&2
  exit 1
fi

if [ "${1:-}" = "offline" ]; then
  # Generate OpenAPI JSON without running server
  echo "Generating OpenAPI schema offline..."
  SCHEMA_TMP="$ROOT_DIR/.openapi.json"
  cd "$ROOT_DIR/backend"
  python -c "
import json
from app.main import application
schema = application.openapi()
with open('$SCHEMA_TMP', 'w') as f:
    json.dump(schema, f, indent=2)
print('Schema written to $SCHEMA_TMP')
"
  OPENAPI_URL="$SCHEMA_TMP"
fi

echo "Generating TypeScript types from $OPENAPI_URL ..."
npx openapi-typescript "$OPENAPI_URL" -o "$OUTPUT"

echo "Done: $OUTPUT"
