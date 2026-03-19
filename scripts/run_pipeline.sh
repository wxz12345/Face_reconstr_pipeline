#!/usr/bin/env bash
set -euo pipefail

INPUT_PATH="${1:-}"
OUTPUT_ZIP="${2:-}"

if [[ -z "${INPUT_PATH}" || -z "${OUTPUT_ZIP}" ]]; then
  echo "Usage: $0 /path/to/video /path/to/output.zip" >&2
  exit 2
fi

if [[ ! -f "${INPUT_PATH}" ]]; then
  echo "Error: input file does not exist: ${INPUT_PATH}" >&2
  exit 3
fi

echo "[run_pipeline] Starting pipeline for: ${INPUT_PATH}"
echo "[run_pipeline] Output zip will be: ${OUTPUT_ZIP}"
echo "[run_pipeline] Simulating processing..."
sleep 3

python ./scripts/script.py "${INPUT_PATH}" "${OUTPUT_ZIP}"

echo "[run_pipeline] Done. Zip created at: ${OUTPUT_ZIP}"

exit 0

