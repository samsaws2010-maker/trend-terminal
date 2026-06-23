#!/usr/bin/env bash
# ──────────────────────────────────────────────
# The Trend Terminal — startup script (Mac/Linux)
# Run this from the project root after setup.
# ──────────────────────────────────────────────

set -e

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "──────────────────────────────────────"
echo " Starting The Trend Terminal"
echo "──────────────────────────────────────"

# 1. Python classifier service (port 5100)
echo "[1/3] Starting Python classifier service on :5100 ..."
python3 artifacts/api-server/python/classifier_service.py &
PYTHON_PID=$!

# 2. Node API server (port 8080)
echo "[2/3] Starting Node API server on :8080 ..."
pnpm --filter @workspace/api-server run dev &
NODE_PID=$!

# 3. Frontend (port 5173 by default)
echo "[3/3] Starting frontend on :5173 ..."
pnpm --filter @workspace/trend-terminal run dev &
FRONTEND_PID=$!

echo ""
echo "✓ All services started."
echo "  Frontend  → http://localhost:5173"
echo "  API       → http://localhost:8080"
echo "  Classifier→ http://localhost:5100"
echo ""
echo "Press Ctrl+C to stop everything."

trap "kill $PYTHON_PID $NODE_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
