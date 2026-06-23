# The Trend Terminal

A stock research dashboard with AI-scored daily picks, market sentiment analysis, live stock charts, and fundamentals. Runs on your PC or any cloud host.

## What It Does

- **AI Daily Picks** — 10 large-cap stocks graded A-F based on fundamentals
- **Small & Mid Cap Spotlight** — 6 high-growth picks refreshed every 2 hours
- **Market Sentiment** — 0-100 score from live news across 20 market indices
- **Live Stock Charts** — 1-year and all-time OHLCV data with today's price
- **Fundamentals** — P/E, market cap, beta, debt ratios, analyst targets
- **Search Any Ticker** — Instant lookup with 1,600+ tickers in the universe
- **Watchlist** — Follow your favorite stocks, persist across sessions

## Data Sources (All Free — No API Keys Needed)

| Source | What It Provides | How It's Used |
|--------|-----------------|---------------|
| **Yahoo Finance** | Stock prices, OHLCV charts, analyst targets | Primary chart data source |
| **Finviz** | P/E, market cap, beta, debt/equity, profit margins, analyst consensus | Stock fundamentals + scoring engine |
| **Google News RSS** | Live news headlines for any ticker | Sentiment analysis (Positive/Negative/Neutral) |
| **Wikipedia** | S&P 500, NASDAQ-100, S&P 400, S&P 600 ticker lists | Universe of stocks to score |
| **Stooq** (Polish Exchange) | Historical OHLCV data | Chart fallback when Yahoo Finance fails |
| **AlphaVantage** | Market movers, top gainers/losers | Market movers + fallback data |

All data is fetched live using your own WiFi. No paid subscriptions, no API keys required.

## Tech Stack

- **Frontend:** React + Vite + Tailwind CSS + Recharts
- **API Server:** Node.js + Express (port 8080)
- **Data Service:** Python + Flask (port 5100)
- **Database:** SQLite (hourly snapshots, daily picks cache)
- **Package Manager:** pnpm workspaces

## Quick Start (Local PC)

### Prerequisites

| Tool | Download | Check |
|------|----------|-------|
| **Node.js** | https://nodejs.org (LTS) | `node --version` |
| **pnpm** | `npm install -g pnpm` | `pnpm --version` |
| **Python 3** | https://python.org | `python3 --version` |

### Run It

```bash
# Windows
double-click start-local.bat

# Mac / Linux
./start-local.sh
```

Wait 30 seconds for the first data load, then open: **http://localhost:3000**

## Deploy to Render (Free, Permanent)

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
4. Render reads the `docker-compose.yml` and deploys everything
5. Your app is live at `https://your-app.onrender.com`

### Step 3: Custom Domain (Optional)

1. In Render dashboard → Settings → Custom Domains
2. Add your domain (e.g., `trendterminal.com`)
3. Copy the DNS records
4. Go to your domain registrar (Namecheap, Cloudflare, etc.)
5. Paste the DNS records
6. Wait 5-30 minutes

## How Data Stays Fresh

| Feature | Refresh Rate | Data Source |
|---------|-------------|-------------|
| AI Daily Picks | Daily at midnight UTC | Finviz + Wikipedia + scoring algorithm |
| Small/Mid Cap Spotlight | Every 2 hours | Finviz + scoring algorithm |
| Market Sentiment | Every 6 hours | Google News RSS (20 market indices) |
| Stock Charts | Every 1 hour | Yahoo Finance (primary), Stooq (fallback) |
| Live Prices | Every 5 minutes | Finviz + Yahoo Finance |
| News Sentiment | On demand | Google News RSS (per ticker) |

## Recurring Infrastructure

1. **Frontend auto-refresh** — Every 5 minutes, fetches fresh picks, sentiment, movers
2. **Daily pick rebuild** — At midnight UTC, rescans all S&P 500 + NASDAQ 100 + S&P 400/600, scores every stock, picks top 10
3. **Hourly snapshots** — Saves market data to SQLite for historical tracking
4. **Triple-guard cache** — In-memory + disk cache + date validation prevents stale data
5. **Date-seeded rotation** — Different stock pool every day (seed = today's date)

## File Structure

```
├── artifacts/
│   ├── api-server/
│   │   ├── python/
│   │   │   ├── stock_data_service.py   # Main data engine (Finviz, Yahoo, News)
│   │   │   ├── requirements.txt        # Python dependencies
│   │   │   └── cache/                  # Picks cache + stock detail cache
│   │   └── src/routes/
│   │       ├── index.ts                 # API routes
│   │       └── stocks.ts                # Stock data endpoints
│   └── trend-terminal/
│       ├── src/pages/
│       │   └── stocks.tsx              # Main dashboard UI
│       ├── src/components/            # UI components
│       └── dist/                      # Built frontend
├── lib/
│   ├── api-spec/                     # OpenAPI spec
│   ├── api-client-react/             # Generated React hooks
│   ├── api-zod/                      # Generated Zod schemas
│   └── db/                           # Drizzle schema
├── start-local.sh                    # Mac/Linux starter
├── start-local.bat                   # Windows starter
├── pnpm-workspace.yaml             # Workspace config
├── package.json                     # Root dependencies
├── docker-compose.yml               # Render/Railway deployment
└── README.md                         # This file
```

## Pick Scoring Algorithm

Each stock gets a 0-100 score based on:

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Analyst Consensus | 20 pts | Buy/hold/sell ratings |
| Profit Margin | 20 pts | How efficiently the company makes money |
| Revenue Growth | 15 pts | Year-over-year sales growth |
| Analyst Upside | 15 pts | Gap between current price and analyst target |
| Valuation (P/E + EV) | 15 pts | Whether the stock is cheap or expensive |
| Total Debt (D/E) | 10 pts | Financial leverage risk |
| Free Cash Flow | 10 pts | Cash available after expenses |

Grades: A+ (90-100), A (80-89), B+ (70-79), B (62-69), C (52-61), D (below 52)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Port 3000 already in use" | Close the other app, or change the port in `start-local.sh` |
| "Python module not found" | Run `pip3 install -r artifacts/api-server/python/requirements.txt` |
| "pnpm not found" | Run `npm install -g pnpm` |
| "Charts don't load" | Wait 30 seconds for Python to warm up |
| "Picks show empty" | Wait 1 minute for the first data load |
| "Finviz rate limit" | Normal — the app uses cached data |
| No data on July 1 | The date check forces a fresh rebuild automatically |

## License

MIT. Free to use, modify, and deploy anywhere.
