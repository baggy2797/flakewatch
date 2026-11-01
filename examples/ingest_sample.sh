#!/usr/bin/env bash
# Feed each synthetic sample run to flakewatch in order, accumulating history in $DB,
# then print the final report. Usage: examples/ingest_sample.sh [db] [outdir]
set -euo pipefail
DB="${1:-.flakewatch/history.db}"
OUT="${2:-.flakewatch/out}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUT"
# RUN_LIMIT=N ingests only the first N runs (used by the self-test workflow).
for run in $(ls -d "$HERE"/sample/run-* | head -n "${RUN_LIMIT:-999}"); do
  flakewatch analyze "$run" --db "$DB" --run-id "sample-$(basename "$run")" \
    --commit "$(cat "$run/commit.txt")" --json-out "$OUT/report.json" --md-out "$OUT/report.md" 2>/dev/null
done
flakewatch quarantine "$OUT/report.json" --file "$OUT/quarantine.json"
flakewatch comment "$OUT/report.json" --quarantine-file "$OUT/quarantine.json" --out "$OUT/comment.md"
