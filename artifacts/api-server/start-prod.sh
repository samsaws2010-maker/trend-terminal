#!/usr/bin/env bash
set -e

echo "[prod] Starting Python classifier on :5100..."
python3 artifacts/api-server/python/classifier_service.py &

echo "[prod] Waiting for classifier to be ready..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:5100/health > /dev/null 2>&1; then
    echo "[prod] Classifier ready."
    break
  fi
  sleep 1
done

echo "[prod] Starting Node API on :8080..."
exec node --enable-source-maps artifacts/api-server/dist/index.mjs
