# The Trend Terminal — GitHub Deployment Guide

## Quick Deploy Options

### Option 1: Docker (Recommended — Works Anywhere)

```bash
# 1. Clone/unzip the project
cd trend-terminal

# 2. One command to start everything
docker-compose up -d

# 3. Open http://localhost:3000
```

**Requirements:** Docker + Docker Compose

---

### Option 2: Manual Setup (Node.js + Python)

```bash
# 1. Prerequisites
#    - Node.js 24+
#    - Python 3.11+
#    - pnpm (npm install -g pnpm)

# 2. One command setup
./setup.sh

# 3. Start three terminals
# Terminal 1: python3 artifacts/api-server/python/classifier_service.py
# Terminal 2: pnpm --filter @workspace/api-server run dev
# Terminal 3: pnpm --filter @workspace/trend-terminal run dev

# 4. Open http://localhost:3000
```

---

### Option 3: GitHub Pages (Frontend Only — NO DATA)

You can deploy the frontend to GitHub Pages, but it will show empty/no data because the API backend won't be running.

```bash
# Build frontend
cd artifacts/trend-terminal
pnpm run build

# The dist/ folder contains static files
# Deploy dist/ to GitHub Pages
```

**Note:** This only shows the UI shell. All data (picks, sentiment, charts) requires the backend.

---

## What Works Instantly

| Feature | Needs Backend? | Works on GitHub Pages? |
|---------|---------------|----------------------|
| AI Daily Picks | ✓ Yes | ✗ No |
| Market Sentiment | ✓ Yes | ✗ No |
| Stock Charts | ✓ Yes | ✗ No |
| Top 10 Market Cap | ✓ Yes | ✗ No |
| Stock Detail | ✓ Yes | ✗ No |
| Search | ✓ Yes | ✗ No |

---

## Full Stack Required

The Trend Terminal requires 3 running services:

1. **Python Classifier** (port 5100) — Fetches stock data, runs sentiment analysis, generates AI picks
2. **Express API Server** (port 8080) — Routes frontend requests to Python service
3. **React Frontend** (port 3000) — UI that calls the API server

All three must be running for the app to work.

---

## Data Freshness

| Data | Update Frequency | Cache |
|------|-----------------|-------|
| AI Picks | Daily (midnight UTC) | 2 hours |
| Market Sentiment | Every 6 hours | 30 minutes |
| Stock Charts | On request | 1 hour |
| Stock Detail | On request | 15 minutes |
| Top 10 Market Cap | On request | 1 hour |

---

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `PYTHON_SERVICE_PORT` | No | 5100 |
| `PORT` | No | 8080 |
| `DATABASE_URL` | No | SQLite |
| `BASE_PATH` | No | /api |

---

## For Instant Presentation

**Best option:** Use the Docker setup. One command (`docker-compose up -d`) and it's running at `localhost:3000`.

**For demos:** The app works immediately after starting — data is fetched live from Yahoo Finance, Finviz, and Google News. No API keys needed.
