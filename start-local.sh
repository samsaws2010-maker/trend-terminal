#!/bin/bash
# The Trend Terminal — Local PC Starter
# Run this one script to start all 3 services on your PC

set -e

echo "============================================"
echo "  The Trend Terminal — Local PC Starter"
echo "============================================"
echo ""

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "❌ Node.js not found. Download from https://nodejs.org"; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "❌ pnpm not found. Run: npm install -g pnpm"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 not found. Download from https://python.org"; exit 1; }

echo "✅ All prerequisites found!"
echo ""

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "🔄 Installing dependencies (first time only, takes ~2 minutes)..."
    pnpm install
fi

# Check if Python dependencies are installed
if ! python3 -c "import flask, pandas, requests, yfinance" 2>/dev/null; then
    echo "🔄 Installing Python dependencies (first time only)..."
    pip3 install -r artifacts/api-server/python/requirements.txt --quiet
fi

echo ""
echo "🚀 Starting The Trend Terminal..."
echo ""

# Start Python stock data service in background
echo "[1/3] Starting Python stock data service (port 5100)..."
python3 artifacts/api-server/python/stock_data_service.py &
PYTHON_PID=$!
echo "      Python data service PID: $PYTHON_PID"

# Wait for Python to start
sleep 5

# Start API server in background
echo "[2/3] Starting API server (port 8080)..."
pnpm --filter @workspace/api-server run dev &
API_PID=$!
echo "      API server PID: $API_PID"

# Wait for API to start
sleep 5

# Start frontend in background
echo "[3/3] Starting frontend (port 3000)..."
pnpm --filter @workspace/trend-terminal run dev &
FRONTEND_PID=$!
echo "      Frontend PID: $FRONTEND_PID"

echo ""
echo "============================================"
echo "  ✅ All services started!"
echo ""
echo "  🌐 Open http://localhost:3000 in your browser"
echo ""
echo "  📊 The app uses YOUR PC's WiFi to fetch:"
echo "     • Yahoo Finance (prices, charts)"
echo "     • Finviz (stock details)"
echo "     • Google News (sentiment)"
echo ""
echo "  ⏰ Data refreshes automatically:"
echo "     • AI picks: daily at midnight"
echo "     • Sentiment: every 6 hours"
echo "     • Prices: every 5 minutes"
echo ""
echo "  ⚠️  Press Ctrl+C to stop all services"
echo "============================================"
echo ""

# Wait for Ctrl+C
trap "echo ''; echo '🛑 Stopping all services...'; kill $PYTHON_PID $API_PID $FRONTEND_PID 2>/dev/null; exit 0" INT
wait
