#!/usr/bin/env bash
# Runs one load test from the load generator, and saves its summary under results/.
#   BASE_URL=http://10.0.0.5:8080 loadtest/run.sh normal 10:5m,25:5m
set -euo pipefail

: "${BASE_URL:?Set BASE_URL to the test stack, never production}"
scenario="$1"
stages="$2"
name="${3:-$scenario}"
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$here/results"
chmod 777 "$here/results"

docker run --rm --network host -v "$here:/loadtest" \
  -e BASE_URL="$BASE_URL" -e SCENARIO="$scenario" -e STAGES="$stages" -e RAMP="${RAMP:-30s}" \
  grafana/k6:latest run --quiet --summary-export "/loadtest/results/$name.json" /loadtest/trip.js
