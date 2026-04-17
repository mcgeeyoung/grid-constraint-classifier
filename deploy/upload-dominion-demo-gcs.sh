#!/usr/bin/env bash
# Upload the Dominion static demo (app/static/dominion_demo) to a GCS prefix and
# inject the public API base URL into config.js for browser calls to Cloud Run (or any HTTPS API).
#
# Required env:
#   GCS_DEMO_BUCKET          e.g. wattcarbon-dominion-demo
#   DOMINION_API_PUBLIC_URL  full path prefix, e.g. https://YOUR-SERVICE-abc123.us-central1.run.app/api/v1/dominion
#
# Optional:
#   GCS_DEMO_PREFIX   object prefix, e.g. dominion-demo (no leading/trailing slashes)
#
# Example:
#   export GCS_DEMO_BUCKET=my-demo-bucket
#   export DOMINION_API_PUBLIC_URL=https://gridclass-api-xxxxx.run.app/api/v1/dominion
#   export GCS_DEMO_PREFIX=dominion-demo
#   ./deploy/upload-dominion-demo-gcs.sh
#
# Then open:
#   https://storage.googleapis.com/${GCS_DEMO_BUCKET}/${GCS_DEMO_PREFIX}/index.html
#
# API CORS: set Cloud Run env CORS_EXTRA_ORIGINS=https://storage.googleapis.com (and any custom
# static domain) so the browser can call the API from this page.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/app/static/dominion_demo"

: "${GCS_DEMO_BUCKET:?Set GCS_DEMO_BUCKET (bucket name only)}"
: "${DOMINION_API_PUBLIC_URL:?Set DOMINION_API_PUBLIC_URL to https://.../api/v1/dominion}"

if [[ "${DOMINION_API_PUBLIC_URL}" != https://* ]]; then
  echo "DOMINION_API_PUBLIC_URL must start with https://" >&2
  exit 1
fi

BUCKET="${GCS_DEMO_BUCKET#gs://}"
BUCKET="${BUCKET%/}"
PREFIX="${GCS_DEMO_PREFIX:-}"
PREFIX="${PREFIX#/}"
PREFIX="${PREFIX%/}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

cp -a "${SRC}/." "${TMP}/"

export DOMINION_API_PUBLIC_URL
export DOMINION_TMP="${TMP}"
python3 <<'PY'
import json, os
from pathlib import Path

url = os.environ["DOMINION_API_PUBLIC_URL"]
base = Path(os.environ["DOMINION_TMP"])
(base / "config.js").write_text(
    "window.__DOMINION_API_BASE__ = " + json.dumps(url) + ";\n",
    encoding="utf-8",
)
PY

if [[ -n "${PREFIX}" ]]; then
  DEST="gs://${BUCKET}/${PREFIX}/"
  PUBLIC_URL="https://storage.googleapis.com/${BUCKET}/${PREFIX}/index.html"
else
  DEST="gs://${BUCKET}/"
  PUBLIC_URL="https://storage.googleapis.com/${BUCKET}/index.html"
fi

# No --delete on destination: avoids wiping unrelated objects if you reuse a bucket.
if command -v gsutil >/dev/null 2>&1; then
  gsutil -m rsync -r "${TMP}/" "${DEST}"
elif command -v gcloud >/dev/null 2>&1; then
  gcloud storage rsync --recursive "${TMP}/" "${DEST}"
else
  echo "Install Google Cloud SDK (gsutil or gcloud)." >&2
  exit 1
fi

echo ""
echo "Uploaded to ${DEST}"
echo "Open: ${PUBLIC_URL}"
echo ""
echo "If objects are not world-readable, grant objectViewer for demo access (e.g. allUsers on this bucket only in non-prod)."
