# The Trend Terminal — Deploy to GitHub + Render

## Quick Start (GitHub → Render)

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOURNAME/YOURREPO.git
git push -u origin main
```

### Step 2: Deploy to Render

1. Go to https://render.com → Sign up free
2. Click "New" → "Blueprint"
3. Connect your GitHub repo
4. Render reads the `docker-compose.yml` and deploys all 3 services:
   - **Python Data Service** (port 5100) — stock data engine
   - **API Server** (port 8080) — Express proxy
   - **Frontend** (port 3000) — React dashboard
5. Your app is live at `https://your-app.onrender.com`

### Step 3: Custom Domain (Optional)

1. In Render dashboard → Settings → Custom Domains
2. Add your domain (e.g., `trendterminal.com`)
3. Copy the DNS records
4. Go to your domain registrar (Namecheap, Cloudflare, etc.)
5. Paste the DNS records
6. Wait 5-30 minutes

---

## What's In This Repo

| Component | Tech | What It Does |
|-----------|------|-------------|
| **Frontend** | React + Vite + Tailwind | Dashboard UI, charts, search, watchlist |
| **API Server** | Express + Node.js | Proxies frontend requests to Python service |
| **Data Service** | Python + Flask | Fetches live data, scores stocks, caches results |
| **Database** | SQLite | Hourly snapshots, daily picks cache |

---

## Data Sources (All Free — No API Keys)

| Source | What It Provides | How It's Used |
|--------|-----------------|---------------|
| **Yahoo Finance** | Stock prices, OHLCV charts | Primary chart data |
| **Finviz** | P/E, market cap, beta, debt, profit margins, analyst targets | Fundamentals + scoring |
| **Google News RSS** | Live news headlines | Sentiment analysis |
| **Wikipedia** | S&P 500, NASDAQ-100, S&P 400/600 tickers | Stock universe |
| **Stooq** | Historical OHLCV data | Chart fallback |
| **AlphaVantage** | Market movers, gainers | Movers + fallback |

---

## How Data Stays Fresh

| Feature | Refresh Rate |
|---------|-------------|
| AI Daily Picks | Daily at midnight UTC |
| Small/Mid Cap Spotlight | Every 2 hours |
| Market Sentiment | Every 6 hours |
| Stock Charts | Every 1 hour |
| Live Prices | Every 5 minutes |
| News Sentiment | On demand |

---

## Local Development

```bash
# Windows
double-click start-local.bat

# Mac / Linux
./start-local.sh
```

Wait 30 seconds, then open: http://localhost:3000

---

## Prerequisites

| Tool | Download | Check |
|------|----------|-------|
| Node.js | https://nodejs.org (LTS) | `node --version` |
| pnpm | `npm install -g pnpm` | `pnpm --version` |
| Python 3 | https://python.org | `python3 --version` |

---

## File Structure

```
├── artifacts/
│   ├── api-server/
│   │   ├── python/
│   │   │   ├── stock_data_service.py   # Main data engine
│   │   │   ├── requirements.txt        # Python deps
│   │   │   └── cache/                  # Data cache
│   │   └── src/routes/              # API endpoints
│   └── trend-terminal/
│       ├── src/pages/stocks.tsx      # Main UI
│       └── dist/                    # Built frontend
├── lib/                        # Shared libraries
├── docker-compose.yml          # Render deployment
├── Dockerfile.*                # Service containers
├── start-local.sh              # Mac/Linux starter
├── start-local.bat             # Windows starter
└── README.md                   # Full documentation
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Port 3000 already in use" | Change the port in `start-local.sh` |
| "Python module not found" | Run `pip3 install -r artifacts/api-server/python/requirements.txt` |
| "pnpm not found" | Run `npm install -g pnpm` |
| "Charts don't load" | Wait 30 seconds for Python to warm up |
| "Picks show empty" | Wait 1 minute for the first data load |
| No data on July 1 | The date check forces a fresh rebuild automatically |
