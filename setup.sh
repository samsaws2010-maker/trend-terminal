#!/bin/bash
set -e

echo "=== The Trend Terminal — One-Click Setup ==="
echo ""

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js not found. Install Node.js 24+ first."; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "ERROR: pnpm not found. Install with: npm install -g pnpm"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3 not found. Install Python 3.11+ first."; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "ERROR: pip3 not found."; exit 1; }

echo "[1/5] Installing Python dependencies..."
pip3 install -r artifacts/api-server/python/requirements.txt --quiet

echo "[2/5] Installing Node.js dependencies (this takes ~2 minutes)..."
pnpm install

echo "[3/5] Building all packages..."
pnpm run build

echo "[4/5] Setting up Python cache directory..."
mkdir -p artifacts/api-server/python/cache

echo "[5/5] Setup complete!"
echo ""
echo "=== Start the app ==="
echo ""
echo "Terminal 1 — Python classifier (port 5100):"
echo "  python3 artifacts/api-server/python/classifier_service.py"
echo ""
echo "Terminal 2 — API server (port 8080):"
echo "  pnpm --filter @workspace/api-server run dev"
echo ""
echo "Terminal 3 — Frontend (port 3000):"
echo "  pnpm --filter @workspace/trend-terminal run dev"
echo ""
echo "Then open http://localhost:3000 in your browser"
