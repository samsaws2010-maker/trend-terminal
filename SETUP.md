# The Trend Terminal — Portable Setup Guide

A dark-terminal WSB meme-stock sentiment dashboard with AI-powered stock picks, research drill-downs, and a "beat the AI" sentiment classification game.

## Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| Node.js | 20+ | https://nodejs.org |
| pnpm | 9+ | `npm install -g pnpm` |
| Python | 3.11+ | https://python.org |

---

## Step 1 — Environment variables

```bash
cp .env.example .env
```

The defaults in `.env.example` work out of the box. No edits needed unless you want to change ports.

Optional:
- Add `OPENAI_API_KEY=sk-...` for the AI sentiment classifier
- Change `PORT` values if you have conflicts

---

## Step 2 — Install Node dependencies

```bash
pnpm install
```

---

## Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Step 4 — Start everything

**Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```
double-click start.bat
```

**Or in three separate terminals:**
```bash
# Terminal 1 — Python classifier
python3 artifacts/api-server/python/classifier_service.py

# Terminal 2 — Node API
PORT=8080 pnpm --filter @workspace/api-server run dev

# Terminal 3 — Frontend
PORT=5173 BASE_PATH=/ pnpm --filter @workspace/trend-terminal run dev
```

---

## Step 5 — Open the app

```
http://localhost:5173
```

---

## Ports

| Service | Port |
|---------|------|
| Frontend (Vite) | 5173 |
| Node API | 8080 |
| Python Classifier | 5100 |

---

## Troubleshooting

**"Picks section spinning forever"** — normal on first run. The Python service pre-loads ~600 stock tickers from Finviz. This takes 60–120 seconds. It caches everything after that.

**"Shuffle button is slow"** — after the first run, all data is cached. Subsequent shuffles will be fast.

**Port already in use** — change the port in `.env` or kill the existing process.

**OpenAI key** — optional. The app works without it. If you add one, it enables AI-powered sentiment classification for the "beat the AI" game.
