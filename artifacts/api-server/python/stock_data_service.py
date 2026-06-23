"""
stock_data_service.py — Flask microservice for stock research dashboard
Provides AI picks, market sentiment, stock charts, and fundamentals.
"""
import os
import sys
import json
import math
import re
import hashlib
import threading
import urllib.parse
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

# Persistent disk cache for picks — uses workspace dir (survives deploys in Replit)
_CACHE_DIR = Path(__file__).resolve().parent / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_PICKS_DISK_PATH = _CACHE_DIR / "picks_cache.json"
_DETAIL_DISK_PATH = _CACHE_DIR / "stock_detail_cache.json"

import pandas as pd

app = Flask(__name__)
CORS(app)


def _safe(val):
    """Convert NaN/inf to None for JSON serialisation."""
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


# ── Shared web scraping helpers ───────────────────────────

import requests
from datetime import datetime, timedelta

_WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Yahoo Finance headers (browser-like to avoid 403)
_YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Chart cache: ticker -> {"ts": float, "data": list, "last_date": str}
_CHART_CACHE: dict[str, dict] = {}
_CHART_CACHE_TTL = 3600  # 1 hour — chart data
_CHART_MAX_RETRIES = 3
_CHART_BACKOFF = 2.0  # seconds between retries

# In-memory cache for stock data (TTL: 5 minutes)
_STOCK_CACHE: dict[str, dict] = {}
_STOCK_CACHE_TTL = 900   # 15 minutes — live price data refreshes often

# Finviz headers (keep them lightweight)
_FINVIZ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _parse_dividend_yield(raw: dict) -> float | None:
    """Extract dividend yield from Finviz raw data.  Returns 0.0 for non-dividend payers.
    Handles: 'Dividend %' (legacy) or 'Dividend TTM' (e.g. '2.10 (0.36%)') or 'Dividend Est.'.
    """
    import re
    # 1. Try legacy 'Dividend %' field (percentage directly)
    val = raw.get("Dividend %", "").strip()
    if val and val != "-" and val != "N/A" and val != "":
        parsed = _parse_finviz_val(val)
        if parsed is not None:
            return parsed
    # 2. Try 'Dividend TTM' or 'Dividend Est.' — format like "2.10 (0.36%)"
    for key in ("Dividend TTM", "Dividend Est."):
        val = raw.get(key, "").strip()
        if val and val != "-" and val != "N/A" and val != "":
            # Extract percentage from parentheses
            m = re.search(r"\(([0-9]+\.?[0-9]*)%\)", val)
            if m:
                try:
                    return float(m.group(1)) / 100
                except (ValueError, TypeError):
                    pass
            # Also try direct percentage
            parsed = _parse_finviz_val(val)
            if parsed is not None:
                return parsed
    # 3. No dividend found — return 0.0 for non-dividend payers
    # We can tell if it's truly no dividend if the company has other data
    return 0.0


def _parse_finviz_val(val: str):
    """Parse a Finviz value string into a float, handling B/M/K/%, dashes, and 52W high/low."""
    if val is None or val.strip() == "" or val.strip() == "-":
        return None
    val = val.strip()
    # Remove commas
    val = val.replace(",", "")
    import re

    # 1. Pure percentage: "27.15%", "-6.33%", "+5.2%"
    # Capture the sign + number together so negatives are preserved
    m = re.match(r"^([+-]?[0-9]+\.?[0-9]*)%$", val)
    if m:
        try:
            return float(m.group(1)) / 100
        except (ValueError, TypeError):
            return None

    # 2. 52W High/Low: "317.40-6.33%" or "195.0752.41%" — extract the price part
    m = re.match(r"^([0-9]+\.?[0-9]*)\s*[+-]?[0-9]+\.?[0-9]*%$", val)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, TypeError):
            return None

    # 3. B/M/K suffixes (e.g., "4.66B", "155.89M", "1.5K")
    mult = 1
    if val.endswith("B"):
        mult = 1e9
        val = val[:-1]
    elif val.endswith("M"):
        mult = 1e6
        val = val[:-1]
    elif val.endswith("K"):
        mult = 1e3
        val = val[:-1]
    try:
        return float(val) * mult
    except (ValueError, TypeError):
        return None


def _parse_finviz_price(val: str):
    """Parse a price string like '$297.27' or '297.27'."""
    if val is None:
        return None
    val = val.strip().replace("$", "")
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _fetch_finviz(ticker: str) -> dict | None:
    """Fetch stock data by scraping Finviz (no API key needed)."""
    from bs4 import BeautifulSoup
    import re
    tk = ticker.upper()
    now = datetime.now().timestamp()
    if tk in _STOCK_CACHE:
        entry = _STOCK_CACHE[tk]
        if now - entry.get("ts", 0) < _STOCK_CACHE_TTL:
            return entry["data"]
    try:
        url = f"https://finviz.com/quote.ashx?t={tk}"
        r = requests.get(url, headers=_FINVIZ_HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"[finviz] {tk} HTTP {r.status_code}", flush=True)
            return None
        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract all metrics from the snapshot table
        raw: dict[str, str] = {}
        for table in soup.find_all("table", class_="snapshot-table2"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                for i in range(0, len(cells), 2):
                    if i + 1 < len(cells):
                        label = cells[i].get_text(strip=True)
                        value = cells[i + 1].get_text(strip=True)
                        raw[label] = value

        if not raw:
            print(f"[finviz] {tk} no snapshot data found", flush=True)
            return None

        # Extract price, change, and name from the page
        price = _parse_finviz_val(raw.get("Price", ""))
        change_pct = _parse_finviz_val(raw.get("Change", ""))
        market_cap = _parse_finviz_val(raw.get("Market Cap", ""))
        # Name: get from page title or ticker
        name = tk
        for m in re.finditer(r"- ([^<]+) Stock", html):
            name = m.group(1).strip()
            break
        # Get sector and industry from the page
        sector = "Unknown"
        industry = ""
        # Finviz uses <a> screener links for sector/industry
        for m in re.finditer(r'<a href="screener\?v=111&f=sec_[^"]+" class="tab-link"[^>]*>([^<]+)</a>', html):
            sector = m.group(1).strip()
        for m in re.finditer(r'<a href="screener\?v=111&f=ind_[^"]+" class="tab-link[^"]*"[^>]*>([^<]+)</a>', html):
            industry = m.group(1).strip()

        # Parse all metrics
        data = {
            "name": name,
            "regularMarketPrice": price,
            "currentPrice": price,
            "change_pct": change_pct,
            "marketCap": market_cap,
            "sector": sector,
            "industry": industry,
            "trailingPE": _parse_finviz_val(raw.get("P/E", "")),
            "forwardPE": _parse_finviz_val(raw.get("Forward P/E", "")),
            "priceToBook": _parse_finviz_val(raw.get("P/B", "")),
            "trailingEps": _parse_finviz_val(raw.get("EPS (ttm)", "")),
            "dividendYield": _parse_dividend_yield(raw),
            "profitMargins": _parse_finviz_val(raw.get("Profit Margin", "")),
            "revenueGrowth": _parse_finviz_val(raw.get("Sales Q/Q", "")),
            "debtToEquity": _parse_finviz_val(raw.get("Debt/Eq", "")),
            "currentRatio": _parse_finviz_val(raw.get("Current Ratio", "")),
            "quickRatio": _parse_finviz_val(raw.get("Quick Ratio", "")),
            "returnOnEquity": _parse_finviz_val(raw.get("ROE", "")),
            "returnOnAssets": _parse_finviz_val(raw.get("ROA", "")),
            "beta": _parse_finviz_val(raw.get("Beta", "")),
            "operatingMargins": _parse_finviz_val(raw.get("Oper. Margin", "")),
            "earningsGrowth": _parse_finviz_val(raw.get("EPS Q/Q", "")),
            "fiftyTwoWeekHigh": _parse_finviz_val(raw.get("52W High", "")),
            "fiftyTwoWeekLow": _parse_finviz_val(raw.get("52W Low", "")),
            "totalStockholderEquity": None,
            "totalDebt": _parse_finviz_val(raw.get("Total Debt", "")),
            "enterpriseValue": _parse_finviz_val(raw.get("Enterprise Value", "")),
            "enterpriseToEbitda": _parse_finviz_val(raw.get("EV/EBITDA", "")),
            "recommendationMean": _parse_finviz_val(raw.get("Recom", "")),
            "recommendationKey": raw.get("Recom", ""),
            "numberOfAnalystOpinions": None,
            "targetHighPrice": None,
            "targetLowPrice": None,
            "targetMeanPrice": _parse_finviz_val(raw.get("Target Price", "")),
            "targetMedianPrice": None,
            "freeCashflow": _parse_finviz_val(raw.get("Free Cash Flow", "")),
            # Extra fields for display
            "fiftyTwoWeekHigh": _parse_finviz_val(raw.get("52W High", "")),
            "fiftyTwoWeekLow": _parse_finviz_val(raw.get("52W Low", "")),
            "priceToSales": _parse_finviz_val(raw.get("P/S", "")),
            "peg": _parse_finviz_val(raw.get("PEG", "")),
            "rsi": _parse_finviz_val(raw.get("RSI (14)", "")),
            "avgVolume": _parse_finviz_val(raw.get("Avg Volume", "")),
            "volume": _parse_finviz_val(raw.get("Volume", "")),
            "prevClose": _parse_finviz_val(raw.get("Prev Close", "")),
            "shortRatio": _parse_finviz_val(raw.get("Short Ratio", "")),
            "shortFloat": _parse_finviz_val(raw.get("Short Float", "")),
            "instOwn": _parse_finviz_val(raw.get("Inst Own", "")),
            "insiderOwn": _parse_finviz_val(raw.get("Insider Own", "")),
            "perfWeek": _parse_finviz_val(raw.get("Perf Week", "")),
            "perfMonth": _parse_finviz_val(raw.get("Perf Month", "")),
            "perfQuarter": _parse_finviz_val(raw.get("Perf Quarter", "")),
            "perfYear": _parse_finviz_val(raw.get("Perf Year", "")),
            "perfYTD": _parse_finviz_val(raw.get("Perf YTD", "")),
            "epsNextY": _parse_finviz_val(raw.get("EPS next Y", "")),
            "epsNextQ": _parse_finviz_val(raw.get("EPS next Q", "")),
            "epsNext5Y": _parse_finviz_val(raw.get("EPS next 5Y", "")),
            "epsPast5Y": _parse_finviz_val(raw.get("EPS past 5Y", "")),
            "salesQoq": _parse_finviz_val(raw.get("Sales Q/Q", "")),
            "epsQoq": _parse_finviz_val(raw.get("EPS Q/Q", "")),
            "salesYy": _parse_finviz_val(raw.get("Sales Y/Y", "")),
            "epsYy": _parse_finviz_val(raw.get("EPS Y/Y", "")),
            "grossMargin": _parse_finviz_val(raw.get("Gross Margin", "")),
            "operatingMargin": _parse_finviz_val(raw.get("Oper. Margin", "")),
            "profitMargin": _parse_finviz_val(raw.get("Profit Margin", "")),
            "roe": _parse_finviz_val(raw.get("ROE", "")),
            "roa": _parse_finviz_val(raw.get("ROA", "")),
            "roic": _parse_finviz_val(raw.get("ROIC", "")),
            "ltDebtToEquity": _parse_finviz_val(raw.get("LT Debt/Eq", "")),
            "debtToEquity": _parse_finviz_val(raw.get("Debt/Eq", "")),
            "cashPerShare": _parse_finviz_val(raw.get("Cash/sh", "")),
            "bookPerShare": _parse_finviz_val(raw.get("Book/sh", "")),
            "employees": raw.get("Employees", ""),
            "earningsDate": raw.get("Earnings", ""),
            "ipo": raw.get("IPO", ""),
            "country": raw.get("Country", ""),
        }
        _STOCK_CACHE[tk] = {"ts": now, "data": data}
        print(f"[finviz] {tk} fetched OK", flush=True)
        return data
    except Exception as e:
        print(f"[finviz] {tk} error: {e}", flush=True)
        return None


def _fetch_yahoo_chart(ticker: str, range_: str = "1mo", interval: str = "1d") -> list:
    """Fetch historical chart data from Yahoo Finance v8 endpoint (no auth needed)."""
    tk = ticker.upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range={range_}&interval={interval}"
    try:
        r = requests.get(url, headers=_YAHOO_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        if not result:
            return []
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        if not timestamps or not closes:
            return []
        chart = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            dt = datetime.fromtimestamp(ts)
            chart.append({"date": dt.strftime("%Y-%m-%d"), "close": round(close, 2)})
        return chart
    except Exception:
        return []


def _fetch_yahoo_ohlcv(ticker: str, range_: str = "1y", interval: str = "1d") -> list:
    """Fetch full OHLCV historical chart data with retry logic.
    Returns list of {date, open, high, low, close, volume}."""
    tk = ticker.upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range={range_}&interval={interval}"
    for attempt in range(_CHART_MAX_RETRIES):
        try:
            r = requests.get(url, headers=_YAHOO_HEADERS, timeout=15)
            if r.status_code == 429:
                # Rate limited — wait and retry
                if attempt < _CHART_MAX_RETRIES - 1:
                    time.sleep(_CHART_BACKOFF * (attempt + 1))
                    continue
                return []
            if r.status_code != 200:
                return []
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            if not result:
                return []
            timestamps = result.get("timestamp", [])
            quote = result.get("indicators", {}).get("quote", [{}])[0]
            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])
            if not timestamps or not closes:
                return []
            chart = []
            for ts, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
                if c is None:
                    continue
                dt = datetime.fromtimestamp(ts)
                chart.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "open": round(o, 2) if o is not None else None,
                    "high": round(h, 2) if h is not None else None,
                    "low": round(l, 2) if l is not None else None,
                    "close": round(c, 2),
                    "volume": int(v) if v is not None else None,
                })
            return chart
        except Exception:
            if attempt < _CHART_MAX_RETRIES - 1:
                time.sleep(_CHART_BACKOFF * (attempt + 1))
            continue
    return []


# --- Stooq challenge solver ---

def _solve_stooq_challenge(session: requests.Session) -> bool:
    """Solve Stooq's proof-of-work JavaScript challenge and verify session.
    Returns True if session is verified."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        # Step 1: Get challenge page
        r = session.get("https://stooq.com/q/d/?s=AAPL.US", headers=headers, timeout=15)
        html = r.text
        if "__verify" not in html:
            return True  # Already verified

        # Extract challenge params
        c_match = re.search(r'c=\"([A-Za-z0-9_-]+)\"', html)
        d_match = re.search(r'd=(\d+)', html)
        if not c_match or not d_match:
            return False

        c = c_match.group(1)
        d = int(d_match.group(1))
        target = "0" * d

        # Solve: find n where SHA256(c+n) starts with d zeros
        n = 0
        while True:
            h = hashlib.sha256(f"{c}{n}".encode()).hexdigest()
            if h.startswith(target):
                break
            n += 1
            if n > 500000:
                return False

        # Verify
        v = session.post("https://stooq.com/__verify", data={"c": c, "n": str(n)}, headers=headers, timeout=15)
        return v.status_code == 200
    except Exception:
        return False


def _fetch_stooq_ohlcv(ticker: str) -> list:
    """Fetch OHLCV from Stooq with challenge solving.
    Returns list of {date, open, high, low, close, volume}."""
    tk = ticker.upper()
    session = requests.Session()

    # Solve challenge first
    if not _solve_stooq_challenge(session):
        return []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        # Calculate date range for 1 year
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        d1 = start_date.strftime("%Y%m%d")
        d2 = end_date.strftime("%Y%m%d")

        url = f"https://stooq.com/q/d/?s={tk}.US&c=0&d1={d1}&d2={d2}&i=d"
        r = session.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return []

        html = r.text
        # Stooq returns an HTML table with data
        # Parse the table rows
        chart = []
        # Look for table rows with daily data
        row_matches = re.findall(r'<tr[^>]*>\s*<td[^>]*>(\d{4}-\d{2}-\d{2})</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d,]+)</td>', html)

        for match in row_matches:
            date_str, open_s, high_s, low_s, close_s, volume_s = match
            chart.append({
                "date": date_str,
                "open": round(float(open_s), 2),
                "high": round(float(high_s), 2),
                "low": round(float(low_s), 2),
                "close": round(float(close_s), 2),
                "volume": int(volume_s.replace(",", "")),
            })

        # Sort by date ascending
        chart.sort(key=lambda x: x["date"])
        return chart
    except Exception:
        return []


# --- Web scraping fallback ---

def _fetch_web_ohlcv(ticker: str) -> list:
    """Fetch OHLCV from web scraping (Finviz or alternative).
    Returns list of {date, open, high, low, close, volume} or empty list."""
    tk = ticker.upper()

    # Try Finviz quote page for current price + recent data
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        }
        url = f"https://finviz.com/quote.ashx?t={tk}"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []

        html = r.text
        # Try to extract current price and change from the page
        price_match = re.search(r'class="quote-price"[^>]*>([\d.]+)', html)
        change_match = re.search(r'class="quote-change"[^>]*>([+-]?[\d.]+)', html)

        if not price_match:
            return []

        current_price = float(price_match.group(1))
        today = datetime.now().strftime("%Y-%m-%d")

        # Return a single-point chart (just today's price)
        # This is minimal but at least shows something
        return [{
            "date": today,
            "open": current_price,
            "high": current_price,
            "low": current_price,
            "close": current_price,
            "volume": None,
        }]
    except Exception:
        return []


# --- Today's price append ---

def _append_today_price(chart: list, ticker: str) -> list:
    """Append today's price from Finviz to the chart if market is open.
    Returns updated chart with today's price added if available and not already present.
    Skips CSV data (it's synthetic/demo data, not real market prices)."""
    if not chart:
        return chart

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    # Check if today already in chart
    if chart[-1]["date"] == today_str:
        return chart

    # Check if market is open (Mon-Fri, 9:30 AM - 4:00 PM ET)
    # For now, skip weekends entirely
    if today.weekday() >= 5:
        return chart

    # Try to get real-time price from Finviz (not CSV)
    finviz_data = _fetch_finviz(ticker)
    if finviz_data and finviz_data.get("currentPrice"):
        price = float(finviz_data["currentPrice"])
        change_pct = finviz_data.get("change_pct")
        volume = finviz_data.get("volume")

        # Validate: price should be within 10% of yesterday's close
        # This prevents adding stale/corrupted data
        yesterday_close = chart[-1]["close"] if chart else price
        if yesterday_close and abs(price - yesterday_close) / yesterday_close > 0.10:
            print(f"[chart] {ticker}: Price {price} differs >10% from yesterday {yesterday_close}, skipping append", flush=True)
            return chart

        # Estimate open from yesterday's close + change_pct
        if change_pct is not None:
            est_open = yesterday_close
        else:
            est_open = yesterday_close

        today_point = {
            "date": today_str,
            "open": round(est_open, 2),
            "high": round(max(price, est_open), 2),
            "low": round(min(price, est_open), 2),
            "close": round(price, 2),
            "volume": int(volume) if volume else None,
        }
        chart.append(today_point)
        print(f"[chart] {ticker}: Appended today's price {price} from Finviz", flush=True)
        return chart

    return chart


def _fetch_chart_ohlcv(ticker: str, range_: str = "1y") -> list:
    """Fetch OHLCV chart data with cascading fallback.
    range_: "1y" or "all" (max available data)
    Returns list of {date, open, high, low, close, volume}."""
    tk = ticker.upper()

    # Map range to Yahoo range parameter
    yahoo_range = "max" if range_ == "all" else "1y"

    # 1. Try Yahoo Finance
    chart = _fetch_yahoo_ohlcv(tk, range_=yahoo_range, interval="1d")
    if chart:
        print(f"[chart] {tk}: Yahoo Finance OK ({len(chart)} points, {yahoo_range})", flush=True)
        return _append_today_price(chart, tk)

    # 2. Try Stooq
    print(f"[chart] {tk}: Yahoo failed, trying Stooq...", flush=True)
    chart = _fetch_stooq_ohlcv(tk)
    if chart:
        print(f"[chart] {tk}: Stooq OK ({len(chart)} points)", flush=True)
        return _append_today_price(chart, tk)

    # 3. Try web scraping
    print(f"[chart] {tk}: Stooq failed, trying web...", flush=True)
    chart = _fetch_web_ohlcv(tk)
    if chart:
        print(f"[chart] {tk}: Web OK ({len(chart)} points)", flush=True)
        return _append_today_price(chart, tk)

    print(f"[chart] {tk}: All sources failed", flush=True)
    return []


def _fetch_yahoo_chart_filled(ticker: str, range_: str = "1mo", interval: str = "1d") -> list:
    """Fetch chart data, filling None closes from hourly data when available."""
    chart = _fetch_yahoo_chart(ticker, range_, interval)
    if not chart:
        return chart
    # Check if any recent close is None (the date was skipped in the above)
    # Find the most recent trading day that should have data
    today = datetime.now().date()
    weekday = today.weekday()
    # If today is Mon, last trading day is Fri (today - 3)
    # If today is Tue-Fri, last trading day is yesterday
    if weekday == 0:  # Monday
        last_expected = today - timedelta(days=3)
    elif weekday in [5, 6]:  # Sat/Sun
        # Saturday -> last Friday (today - 1)
        # Sunday -> last Friday (today - 2)
        last_expected = today - timedelta(days=weekday - 4)
    else:
        last_expected = today - timedelta(days=1)

    # Check if the chart has data for the last expected trading day
    last_chart_date = datetime.strptime(chart[-1]["date"], "%Y-%m-%d").date()
    if last_chart_date < last_expected:
        # The last trading day is missing — try to get it from hourly data
        last_close = _get_last_close_from_hourly(ticker, last_expected)
        if last_close is not None:
            chart.append({"date": last_expected.strftime("%Y-%m-%d"), "close": round(last_close, 2)})
    return chart


def _get_last_close_from_hourly(ticker: str, date: datetime.date) -> float | None:
    """Fetch hourly data and return the last valid close for a specific date."""
    tk = ticker.upper()
    # Try a 2-day range with hourly interval
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=2d&interval=1h"
    try:
        r = requests.get(url, headers=_YAHOO_HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        if not result:
            return None
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        target = date.strftime("%Y-%m-%d")
        last_close = None
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            dt = datetime.fromtimestamp(ts)
            if dt.strftime("%Y-%m-%d") == target:
                last_close = close
        return last_close
    except Exception:
        return None


def _daily_change_from_chart(ticker: str) -> float | None:
    """Compute daily change_pct from last two Yahoo chart closes."""
    chart = _fetch_yahoo_chart(ticker, range_="2d", interval="1d")
    if len(chart) >= 2:
        today = chart[-1]["close"]
        yesterday = chart[-2]["close"]
        if yesterday > 0:
            return (today - yesterday) / yesterday
    return None


def _web_fetch_json(url: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(url, headers=_WEB_HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None

def _web_fetch_news(ticker: str, limit: int = 20) -> list:
    """Fetch news articles via Google News RSS — no auth, no Yahoo dependency."""
    import urllib.request
    import xml.etree.ElementTree as ET
    try:
        query = urllib.parse.quote(f"{ticker} stock")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            root = ET.fromstring(r.read())
        articles = []
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title", "").strip()
            if not title:
                continue
            # Google News appends " - Provider" to titles — strip it for cleaner display
            source_el = item.find("source")
            provider = source_el.text.strip() if source_el is not None else "Web"
            if title.endswith(f" - {provider}"):
                title = title[: -(len(provider) + 3)].strip()
            articles.append({
                "title": title,
                "provider": provider,
                "pub_date": item.findtext("pubDate", ""),
                "url": item.findtext("link", ""),
            })
        return articles
    except Exception:
        return []

def _web_fetch_stock_summary(ticker: str) -> dict:
    """DEPRECATED - no Yahoo Finance. Returns empty dict."""
    return {}

def _web_fetch_chart(ticker: str) -> dict:
    """DEPRECATED - no Yahoo Finance. Returns empty dict."""
    return {}

def _web_extract_info(summary: dict) -> dict:
    """DEPRECATED - no longer used. Returns empty dict."""
    return {}

# --- CSV-based stock data (replaces Yahoo Finance) ---

_CSV_PRICES: pd.DataFrame | None = None
_CSV_PRICES_TS: float = 0.0
_CSV_PRICES_TTL = 300  # 5 min — CSV price cache

def _load_csv_prices() -> pd.DataFrame:
    """Load ticker_prices.csv into a DataFrame with caching."""
    global _CSV_PRICES, _CSV_PRICES_TS
    import time
    now = time.time()
    if _CSV_PRICES is not None and now - _CSV_PRICES_TS < _CSV_PRICES_TTL:
        return _CSV_PRICES
    try:
        script_dir = Path(__file__).resolve().parent
        csv_candidates = [
            script_dir / "ticker_prices.csv",
            script_dir / ".." / "ticker_prices.csv",
            script_dir / ".." / ".." / "ticker_prices.csv",
        ]
        path = None
        for c in csv_candidates:
            if c.exists():
                path = str(c)
                break
        if not path:
            return pd.DataFrame()
        df = pd.read_csv(path)
        _CSV_PRICES = df
        _CSV_PRICES_TS = now
        print(f"[csv] Loaded {len(df)} rows from {path}", flush=True)
        return df
    except Exception as e:
        print(f"[csv] failed to load ticker_prices.csv: {e}", flush=True)
        return pd.DataFrame()

def _get_csv_stock_info(ticker: str) -> dict | None:
    """Get stock info from CSV (no Yahoo Finance)."""
    df = _load_csv_prices()
    if df is None or df.empty or "ticker" not in df.columns:
        return None
    row = df[df["ticker"].str.upper() == ticker.upper()]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "ticker": str(r.get("ticker", "")),
        "name": str(r.get("name", "")) if pd.notna(r.get("name")) else None,
        "current_price": float(r.get("current_price", 0)) if pd.notna(r.get("current_price")) else None,
        "price_change_pct": float(r.get("price_change_pct", 0)) if pd.notna(r.get("price_change_pct")) else None,
        "market_cap": float(r.get("market_cap", 0)) if pd.notna(r.get("market_cap")) else None,
        "week_52_high": float(r.get("week_52_high", 0)) if pd.notna(r.get("week_52_high")) else None,
        "week_52_low": float(r.get("week_52_low", 0)) if pd.notna(r.get("week_52_low")) else None,
        "sector": str(r.get("sector", "")) if pd.notna(r.get("sector")) else None,
    }

def _csv_info_to_dict_for_scoring(info: dict) -> dict:
    """Convert CSV info to the flat dict format expected by _compute_grade_score."""
    return {
        "longName": info.get("name"),
        "currentPrice": info.get("current_price"),
        "regularMarketPrice": info.get("current_price"),
        "regularMarketChangePercent": info.get("price_change_pct"),
        "marketCap": info.get("market_cap"),
        "trailingPE": None,
        "forwardPE": None,
        "priceToBook": None,
        "beta": None,
        "trailingEps": None,
        "bookValue": None,
        "sharesOutstanding": None,
        "targetMeanPrice": None,
        "targetHighPrice": None,
        "targetLowPrice": None,
        "recommendationKey": None,
        "recommendationMean": None,
        "numberOfAnalystOpinions": None,
        "enterpriseToEbitda": None,
        "fiftyTwoWeekLow": info.get("week_52_low"),
        "fiftyTwoWeekHigh": info.get("week_52_high"),
        "dividendYield": None,
        "profitMargins": None,
        "revenueGrowth": None,
        "earningsGrowth": None,
        "debtToEquity": None,
        "currentRatio": None,
        "quickRatio": None,
        "returnOnEquity": None,
        "returnOnAssets": None,
        "operatingMargins": None,
        "operatingCashflow": None,
        "freeCashflow": None,
        "totalDebt": None,
        "enterpriseValue": None,
        "totalStockholderEquity": None,
        "sector": info.get("sector"),
        "industry": None,
    }


def _clean_row(row: dict) -> dict:
    return {k: _safe(v) if isinstance(v, float) else v for k, v in row.items()}


# ── Health ─────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"ok": True})


# ── Stocks ─────────────────────────────────────────────────────────────────────

@app.route("/internal/stocks/prices")
def ticker_prices():
    """Return all tickers from the dynamic universe — cached Finviz + CSV fallback."""
    try:
        large, small_mid = _get_universe()
        all_tickers = large + small_mid
        rows = []
        now = datetime.now().timestamp()
        for tk in all_tickers:
            # Check the in-memory cache first (no network request)
            cached = _STOCK_CACHE.get(tk)
            if cached and now - cached.get("ts", 0) < _STOCK_CACHE_TTL:
                yf = cached["data"]
                price = yf.get("currentPrice") or yf.get("regularMarketPrice")
                # Compute grade on-the-fly from cached Finviz data
                grade_s = _compute_grade_score(yf)
                grade = "A" if grade_s >= 75 else "B" if grade_s >= 60 else "C" if grade_s >= 45 else "D" if grade_s >= 30 else "F"
                rows.append({
                    "ticker": tk,
                    "name": yf.get("name") or tk,
                    "current_price": _safe(float(price)) if price is not None else None,
                    "price_change_pct": _safe(float(yf.get("change_pct"))) if yf.get("change_pct") is not None else None,
                    "market_cap": _safe(float(yf.get("marketCap"))) if yf.get("marketCap") is not None else None,
                    "sector": str(yf.get("sector")) if yf.get("sector") and str(yf.get("sector")) not in ("nan", "None") else None,
                    "grade": grade,
                    "grade_score": grade_s,
                })
            else:
                # Fallback to CSV data for the grid
                csv_info = _get_csv_stock_info(tk)
                if csv_info:
                    grade_s = 55
                    mc = csv_info.get("market_cap")
                    if mc:
                        if mc > 1e11: grade_s += 25
                        elif mc > 1e10: grade_s += 15
                    rows.append({
                        "ticker": tk,
                        "name": csv_info["name"] or tk,
                        "current_price": csv_info["current_price"] or None,
                        "price_change_pct": csv_info["price_change_pct"] or None,
                        "market_cap": csv_info["market_cap"] or None,
                        "sector": csv_info["sector"] or None,
                        "grade": "A" if grade_s >= 75 else "B" if grade_s >= 60 else "C" if grade_s >= 45 else "D" if grade_s >= 30 else "F",
                        "grade_score": grade_s,
                    })
                else:
                    rows.append({
                        "ticker": tk,
                        "name": tk,
                        "current_price": None,
                        "price_change_pct": None,
                        "market_cap": None,
                        "sector": None,
                        "grade": "",
                        "grade_score": 0,
                    })
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/internal/stocks/<ticker>")
def stock_info(ticker):
    try:
        yf = _fetch_finviz(ticker.upper())
        if yf:
            price = yf.get("currentPrice") or yf.get("regularMarketPrice")
            return jsonify({
                "ticker": ticker.upper(),
                "name": yf.get("name") or ticker.upper(),
                "sector": yf.get("sector") or "Unknown",
                "industry": yf.get("industry") or "Unknown",
                "current_price": price or 0.0,
                "previous_close": None,
                "price_change": None,
                "price_change_pct": yf.get("change_pct") or 0.0,
                "market_cap": yf.get("marketCap"),
                "week_52_high": yf.get("fiftyTwoWeekHigh"),
                "week_52_low": yf.get("fiftyTwoWeekLow"),
                "description": "",
                "error": None,
            })
        # Fallback to minimal response
        return jsonify({
            "ticker": ticker.upper(),
            "name": ticker.upper(),
            "sector": "Unknown",
            "industry": "Unknown",
            "current_price": 0.0,
            "previous_close": None,
            "price_change": None,
            "price_change_pct": 0.0,
            "market_cap": None,
            "week_52_high": None,
            "week_52_low": None,
            "description": "",
            "error": None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/internal/stocks/<ticker>/history")
def stock_history(ticker):
    """Return historical chart data with caching.
    Query param: period="1y" (default) or "all"
    Returns list of {date, open, high, low, close, volume} objects."""
    tk = _TICKER_ALIASES.get(ticker.upper().replace(".", "-"), ticker.upper().replace(".", "-"))
    period = request.args.get("period", "1y")
    now = datetime.now().timestamp()

    # Check cache (keyed by ticker+period)
    cache_key = f"{tk}:{period}"
    cached = _CHART_CACHE.get(cache_key)
    if cached and (now - cached.get("ts", 0)) < _CHART_CACHE_TTL:
        return jsonify(cached["data"])

    # Fetch fresh with cascading fallback
    chart = _fetch_chart_ohlcv(tk, range_=period)
    if not chart:
        # Return stale cache if available (graceful degradation)
        if cached:
            return jsonify(cached["data"])
        return jsonify({"error": "no_chart_data", "message": "No historical chart data available"}), 502

    # Store in cache
    _CHART_CACHE[cache_key] = {"ts": now, "data": chart}
    return jsonify(chart)


import requests
import os

_AV_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
_AV_CACHE: dict = {}
_AV_CACHE_TTL = 900  # 15 min cache


def _fetch_av_gainers_losers() -> dict:
    """Fetch real market data from Alpha Vantage with caching."""
    global _AV_CACHE
    now = time.time()
    if _AV_CACHE.get("ts", 0) + _AV_CACHE_TTL > now:
        return _AV_CACHE["data"]
    try:
        url = f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={_AV_API_KEY}"
        resp = requests.get(url, timeout=20)
        data = resp.json()
        _AV_CACHE = {"ts": now, "data": data}
        return data
    except Exception as e:
        return {"error": str(e)}


# ── Alpha Vantage Daily OHLC (Market Data) ──────────────────────────────────

_DB_PATH = _CACHE_DIR / "market_data.db"


def _init_db():
    """Create SQLite tables for persistent market data storage."""
    import sqlite3
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_ohlc (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            change_pct REAL,
            prev_close REAL,
            source TEXT,
            fetched_at TEXT,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_ohlc(ticker, date DESC)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hourly_snapshots (
            ticker TEXT NOT NULL,
            snapshot_at TEXT NOT NULL,
            price REAL,
            change_pct REAL,
            PRIMARY KEY (ticker, snapshot_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hourly_snapshot ON hourly_snapshots(ticker, snapshot_at DESC)")
    conn.commit()
    conn.close()


# Initialize DB on module load
_init_db()


_AV_DAILY_CACHE: dict = {}
_AV_DAILY_TTL = 3600  # 60 min cache


def _get_db_ohlc(ticker: str) -> dict | None:
    """Retrieve the most recent daily OHLC for a ticker from the local DB."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM daily_ohlc WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker.upper(),)
        ).fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        print(f"[db] get_ohlc error: {e}", flush=True)
    return None


def _store_db_ohlc(ticker: str, data: dict):
    """Persist daily OHLC data into the local SQLite DB."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("""
            INSERT OR REPLACE INTO daily_ohlc
            (ticker, date, open, high, low, close, volume, change_pct, prev_close, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker.upper(),
            data.get("date"),
            data.get("open"),
            data.get("high"),
            data.get("low"),
            data.get("close"),
            data.get("volume"),
            data.get("change_pct"),
            data.get("prev_close"),
            data.get("source"),
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[db] store_ohlc error: {e}", flush=True)


def _fetch_av_daily_ohlc(ticker: str) -> dict:
    """Fetch previous trading day's OHLCV from Alpha Vantage TIME_SERIES_DAILY.
    Falls back to local SQLite DB if the API is rate-limited or unavailable."""
    global _AV_DAILY_CACHE
    key = ticker.upper()
    now = time.time()

    # 1. In-memory cache
    cached = _AV_DAILY_CACHE.get(key)
    if cached and cached.get("ts", 0) + _AV_DAILY_TTL > now:
        return cached["data"]

    # 2. Local DB fallback
    db_row = _get_db_ohlc(key)
    if db_row:
        # Stale DB data is acceptable when API is rate-limited
        print(f"[av] {key} returning from DB cache", flush=True)
        result = {
            "date": db_row["date"],
            "open": db_row["open"],
            "high": db_row["high"],
            "low": db_row["low"],
            "close": db_row["close"],
            "volume": db_row["volume"],
            "change_pct": db_row["change_pct"],
            "prev_close": db_row["prev_close"],
            "source": db_row["source"],
            "data_type": "previous_trading_day",
            "last_updated": db_row["fetched_at"],
        }
        _AV_DAILY_CACHE[key] = {"ts": now, "data": result}
        return result

    # 3. Chart data fallback (Yahoo Finance — always works)
    try:
        chart = _fetch_chart_ohlcv(key, range_="1mo")
        if chart and len(chart) >= 2:
            last = chart[-1]
            prev = chart[-2]
            close_p = last.get("close", 0)
            prev_close = prev.get("close", close_p)
            change_pct = ((close_p - prev_close) / prev_close * 100) if prev_close else 0
            result = {
                "date": last.get("date", ""),
                "open": last.get("open", close_p),
                "high": last.get("high", close_p),
                "low": last.get("low", close_p),
                "close": close_p,
                "volume": last.get("volume") if last.get("volume") is not None else None,
                "change_pct": round(change_pct, 2),
                "prev_close": prev_close,
                "source": "Yahoo Finance",
                "data_type": "previous_trading_day",
                "last_updated": datetime.now().isoformat(),
            }
            # Persist to local DB so future calls are instant
            _store_db_ohlc(key, result)
            _AV_DAILY_CACHE[key] = {"ts": now, "data": result}
            return result
    except Exception as e:
        print(f"[av] {key} chart fallback failed: {e}", flush=True)

    # 4. Alpha Vantage API (last resort — needs paid key)
    try:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={key}&apikey={_AV_API_KEY}"
        resp = requests.get(url, timeout=20)
        data = resp.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return {"error": "no_daily_data", "raw": data}
        dates = sorted(ts.keys(), reverse=True)
        if not dates:
            return {"error": "no_dates"}
        prev_date = dates[0]
        prev = ts[prev_date]
        try:
            open_p = float(prev.get("1. open", 0))
            high_p = float(prev.get("2. high", 0))
            low_p = float(prev.get("3. low", 0))
            close_p = float(prev.get("4. close", 0))
            volume = int(prev.get("5. volume", 0))
            prev_close = float(ts[dates[1]].get("4. close", close_p)) if len(dates) > 1 else close_p
            change_pct = ((close_p - prev_close) / prev_close * 100) if prev_close else 0
        except (ValueError, TypeError, ZeroDivisionError):
            return {"error": "parse_failed"}
        result = {
            "date": prev_date,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": volume,
            "change_pct": round(change_pct, 2),
            "prev_close": prev_close,
            "source": "Alpha Vantage",
            "data_type": "previous_trading_day",
            "last_updated": datetime.now().isoformat(),
        }
        # Persist to local DB so future API roadblocks don't lose data
        _store_db_ohlc(key, result)
        _AV_DAILY_CACHE[key] = {"ts": now, "data": result}
        return result
    except Exception as e:
        return {"error": str(e)}


@app.route("/internal/stock/market-data/<ticker>")
def stock_market_data(ticker: str):
    """Return previous trading day's OHLCV for a ticker."""
    tk = _TICKER_ALIASES.get(ticker.upper().replace(".", "-"), ticker.upper().replace(".", "-"))
    data = _fetch_av_daily_ohlc(tk)
    if "error" in data:
        return jsonify(data), 502
    return jsonify(data)


@app.route("/internal/stock/market-data/<ticker>/history")
def stock_market_data_history(ticker: str):
    """Return historical daily OHLCV from local DB for a ticker."""
    import sqlite3
    tk = ticker.upper()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM daily_ohlc WHERE ticker = ? ORDER BY date DESC LIMIT 30",
            (tk,)
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _av_item_to_stock(item: dict) -> dict:
    """Convert Alpha Vantage item to our Stock format."""
    try:
        change_str = str(item.get("change_percentage", "0%")).replace("%", "")
        change_pct = float(change_str)
    except (ValueError, TypeError):
        change_pct = 0.0
    try:
        price = float(item.get("price", 0))
    except (ValueError, TypeError):
        price = 0.0
    return {
        "ticker": str(item.get("ticker", "")),
        "name": "",  # Alpha Vantage doesn't provide names
        "price": price,
        "change_pct": change_pct,
        "grade": "",  # No grade from live data
        "grade_score": 0,
    }


def _store_hourly_snapshot(ticker: str, price: float | None, change_pct: float | None):
    """Store an hourly snapshot for computing hourly change."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("""
            INSERT OR REPLACE INTO hourly_snapshots
            (ticker, snapshot_at, price, change_pct)
            VALUES (?, ?, ?, ?)
        """, (ticker.upper(), datetime.now().isoformat(), price, change_pct))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[db] store_hourly error: {e}", flush=True)


def _get_previous_hourly_snapshot(ticker: str) -> dict | None:
    """Retrieve the most recent hourly snapshot before the current hour."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM hourly_snapshots
               WHERE ticker = ? AND snapshot_at < datetime('now', 'start of hour')
               ORDER BY snapshot_at DESC LIMIT 1""",
            (ticker.upper(),)
        ).fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        print(f"[db] get_hourly error: {e}", flush=True)
    return None


def _take_hourly_snapshots():
    """Take hourly snapshots for all tickers in the universe."""
    try:
        large, small_mid = _get_universe()
        all_tickers = list(dict.fromkeys(large + small_mid))
        print(f"[hourly] Taking snapshots for {len(all_tickers)} tickers...", flush=True)
        for tk in all_tickers:
            try:
                data = _fetch_finviz(tk)
                if data:
                    _store_hourly_snapshot(tk, data.get("currentPrice"), data.get("change_pct"))
            except Exception as e:
                print(f"[hourly] {tk} error: {e}", flush=True)
            import time as _t
            _t.sleep(0.05)
        print(f"[hourly] Snapshots complete.", flush=True)
    except Exception as e:
        print(f"[hourly] Snapshot run failed: {e}", flush=True)


# Top 10 stocks by market cap (June 2026) — hardcoded so we always show the real leaders
_TOP_10_MARKET_CAP = [
    "NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "TSLA", "BRK-B", "TSM", "AVGO"
]

def _get_movers() -> dict:
    """Return top 10 market-cap stocks with their current data.
    Fetches data from Finviz for each ticker if not in cache."""
    try:
        import random
        tickers = _TOP_10_MARKET_CAP.copy()
        random.shuffle(tickers)
        tickers_data = []
        for tk in tickers:
            # Check cache first
            data = _STOCK_CACHE.get(tk)
            if not data:
                # Fetch from Finviz if not cached
                yf = _fetch_finviz(tk)
                if yf:
                    data = {"ts": datetime.now().timestamp(), "data": yf}
            if data:
                price = data["data"].get("currentPrice")
                change_pct = data["data"].get("change_pct")
                if price is not None and change_pct is not None:
                    tickers_data.append({
                        "ticker": tk,
                        "price": price,
                        "change_pct": round(change_pct * 100, 2),
                        "name": data["data"].get("name", tk),
                    })
        return {
            "stocks": tickers_data,
            "marketOpen": True,
            "lastUpdated": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.route("/internal/market/movers")
def market_movers():
    """Return top 10 market cap stocks sorted by daily change — top 5 gainers, bottom 5 losers."""
    data = _get_movers()
    if "error" in data:
        return jsonify(data), 500
    return jsonify(data)
# ── Web News Sentiment ────────────────────────────────────────────────────────

import threading
import time

_WEB_CACHE: dict = {}          # ticker -> {"ts": float, "data": dict}
_WEB_CACHE_TTL = 3600        # 1 h cache per ticker (fresh news every hour)

_DEFAULT_TICKERS = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AVGO","TSM","LLY",
    "RDDT","CELH","MARA","HIMS",
    "MCO","SPGI","MSCI",
]


def _web_news_for_ticker(ticker: str) -> dict:
    """Fetch web news for a ticker, classify each headline, return stats."""
    global _WEB_CACHE
    now = time.time()
    cached = _WEB_CACHE.get(ticker)
    if cached and now - cached["ts"] < _WEB_CACHE_TTL:
        return cached["data"]

    try:
        raw_news = _web_fetch_news(ticker.upper(), limit=20)
    except Exception as e:
        print(f"[web_news] Failed to fetch news for {ticker}: {e}", flush=True)
        raw_news = []

    # Ticker-relevance filter — keep articles that mention the ticker or its company name
    def _relevant(title: str, url: str) -> bool:
        t = ticker.upper()
        combined = (title + " " + url).upper()
        # Exact ticker match
        if t in combined:
            return True
        # Company name from reverse ticker map
        for name, mapped in _TICKER_MAP.items():
            if mapped == t and name.upper() in combined:
                return True
        # Hardcoded aliases for short tickers that collide with common words
        # Also includes dot/dash variant mappings
        aliases = {
            "CON": ["CONSOLIDATED", "CONSOLIDATION", "CON EDISON", "CONSOLIDATED EDISON"],
            "APP": ["APPLOVIN", "APP LOVIN"],
            "CAN": ["CANOO", "CANNABIS", "CANADIAN"],
            "US": ["US STEEL", "US CELLULAR", "US FOODS"],
            "BRK-B": ["BRK.B", "BERKSHIRE", "BERKSHIRE HATHAWAY", "BRK"],
            "BRK-A": ["BRK.A", "BERKSHIRE", "BERKSHIRE HATHAWAY", "BRK"],
        }
        for alias in aliases.get(t, []):
            if alias in combined:
                return True
        return False

    articles = []
    pos = neg = neu = 0
    for item in raw_news[:20]:
        title = item.get("title", "").strip()
        if not title:
            continue
        url = item.get("url", "")
        # Relevance filter
        if not _relevant(title, url):
            continue
        provider = item.get("provider", "Web")
        pub_date = item.get("pub_date", "")
        label = _classify_news_sentiment(title)
        if label == "Positive":
            pos += 1
        elif label == "Negative":
            neg += 1
        else:
            neu += 1
        articles.append({
            "title": title,
            "provider": provider,
            "pub_date": pub_date,
            "url": url,
            "label": label,
        })

    # Blended sentiment score: neutral articles count as 0.5 so they
    # pull scores toward centre rather than being ignored entirely.
    # Formula: (pos + neu*0.5) / total — ranges 0-100, anchored at 50 when
    # all articles are neutral. This prevents 1 positive + 9 neutral = 100%.
    total = pos + neg + neu
    if total == 0:
        positive_pct = 50.0
        negative_pct = 50.0
    else:
        positive_pct = round((pos + neu * 0.5) / total * 100, 1)
        negative_pct = round((neg + neu * 0.5) / total * 100, 1)
    neutral_pct = round(neu / (total or 1) * 100, 1)

    if pos > neg:
        dominant = "Positive"
    elif neg > pos:
        dominant = "Negative"
    else:
        dominant = "Neutral"

    data = {
        "ticker": ticker,
        "positive_pct": positive_pct,
        "negative_pct": negative_pct,
        "neutral_pct": neutral_pct,
        "dominant_sentiment": dominant,
        "article_count": len(articles),
        "articles": articles,
    }
    _WEB_CACHE[ticker] = {"ts": now, "data": data}
    return data


@app.route("/internal/market/news-sentiment")
def web_news_sentiment():
    tickers_param = request.args.get("tickers", "")
    if tickers_param:
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
    else:
        tickers = _DEFAULT_TICKERS

    results = [None] * len(tickers)

    def fetch(i, tk):
        results[i] = _web_news_for_ticker(tk)

    threads = [threading.Thread(target=fetch, args=(i, tk)) for i, tk in enumerate(tickers)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=12)

    # Filter out None (timed-out) and return
    output = [r for r in results if r is not None]
    # Sort by positive_pct desc
    output.sort(key=lambda x: x["positive_pct"], reverse=True)
    return jsonify(output)


@app.route("/internal/market/ticker-news/<ticker>")
def web_ticker_news_single(ticker: str):
    """Return web news sentiment for a single arbitrary ticker."""
    data = _web_news_for_ticker(ticker.upper().replace(".", "-"))
    return jsonify(data)


# ── News posts ─────────────────────────────────────────────────────────────────

NEWS_FILE = Path(__file__).resolve().parents[1] / "data" / "news_posts.json"

_news_posts: list = []

def _load_news():
    global _news_posts
    try:
        with open(NEWS_FILE, "r") as f:
            _news_posts = json.load(f)
        print(f"[classifier_service] Loaded {len(_news_posts)} news posts", flush=True)
    except Exception as e:
        print(f"[classifier_service] Failed to load news posts: {e}", flush=True)
        _news_posts = []

_load_news()


_POSITIVE_WORDS = {
    "beats","beat","surges","surge","surged","record","raises","raised","raise",
    "jumps","jumped","jump","soars","soar","soared","profit","profits","growth","grows",
    "wins","win","won","expands","expand","expanded","upgrade","upgrades","upgraded",
    "buyback","dividend","strong","tops","best","exceeds","exceed","exceeded",
    "climbs","climbed","climb","accelerates","accelerate","boosts","boost","boosted",
    "gains","gain","gained","rises","rose","rise","doubles","doubled","double",
    "surpasses","surpassed","outperforms","outperform","highest","record-breaking",
    "tripled","triples","triple","accelerated","approval","approved",
    "all-time","expands","expanding","broadens","momentum",
    "bullish","bull","rally","rallies","rallied","rebound","rebounded","rebounds",
    "recovery","recover","recovered","breakout","breakthrough","milestone",
    "outperformance","initiates","overweight","positive","opportunity","upside",
    "optimistic","optimism","confident","confidence","acceleration","target","buy",
    "strong-buy","investment-grade","returning","awarded","partnership","deal",
    "renewed","buyout","acquisition","merger","synergies","market-share","leading",
    "dominates","dominant","innovative","launch","launched","launches","deployed",
    "ai","breakthrough","demand","exceeding","ahead","new","higher","higher-than",
    "demands","infrastructure","capital","spending","invest","investing","investment",
    "undervalued","cheap","attractive","undervalued",
    "premium","defensive","resilient","solid",
    "outperform","upgrade","upgraded","reinitiates","reinitiate",
    "overweight","add","accumulate","long",
    "success","successful","succeed","delivers","deliver",
    "earnings","eps","ebitda","revenue","revenues",
    "profitability","free cash","cash flow","fcf","dividend",
    "shareholder","shareholders","returns","returning",
    "expanding","expansion","growth","growing",
}

_NEGATIVE_WORDS = {
    "misses","miss","missed","falls","fall","fell","cuts","cut","layoffs","layoff",
    "slashes","slash","slashed","drops","drop","dropped","declines","decline","declined",
    "narrows","concern","delays","delay","delayed","fails",
    "fail","failed","blocked","block","shrinks","shrink","shrunk","disappoints",
    "disappoint","disappointing","collapses","collapse","collapsed","halts","halt",
    "halted","withdraws","withdraw","withdrawn","plunges","plunge","plunged","sinks",
    "sink","sank","tumbles","tumble","tumbled","weaker","weakness","weak","shortage",
    "shortages","recall","recalls","investigation","probe","bankruptcy","crisis",
    "restructuring","restructures","writedown","write-down","impairment","loss","losses",
    "bearish","bear","short","sell","underweight","downgrade","downgraded",
    "overvalued","expensive","bubble","frothy","risky","risk",
    "warning","warn","warns","caution","cautious","red flag",
    "lawsuit","litigation","fine","penalty","scandal","fraud",
    "debt","leverage","burn","burning","cash burn","dilution",
    "slowing","slowed","slow","stagnant","stagnation","plateau",
    "headwinds","headwind","tailwinds","competition","competitive",
    "replace","replacing","replaced","obsolete","obsolescence",
    "losing","lose","lost","loser","defeat","defeated",
    "fire","fired","firing","resign","resigned","resignation","departure",
    "exit","exits","exiting","leave","leaves","left",
    "recession","inflation","deflation","tariff","tariffs",
    "regulatory","regulation","ban","banned","restriction","restrict",
    "delay","delays","delayed","postpone","postponed","shelved",
    "abandon","abandoned","abandoning","cancel","cancelled","canceled",
    "disappointing","disappoint","disappointed","disappointment",
    "underperform","underperforms","underperformance","lag","lags","lagging",
    "volatility","volatile","turbulent","turmoil","uncertainty","uncertain",
    "guidance cut","forecast cut","outlook cut","revenue cut","profit cut",
    "margin contraction","margin compress","margin pressure",
    "earnings miss","revenue miss","sales miss","profit miss",
    "production cut","production halt","supply chain","supply issue",
    "guidance lowered","outlook lowered","forecast lowered",
    "downgrade","downgrades","downgraded",
    "overpriced","price target cut","pt cut","target cut",
    "negative","deteriorate","deteriorating","deteriorated",
    "strain","strained","stress","stressed","pressure","pressured",
    "crunch","squeeze","crisis","trouble","troubled","problem","problems",
    "issue","issues","challenge","challenges","difficult","difficulty",
    "warn","warns","warning","warnings","alert","alerts","red flag",
}


def _classify_news_sentiment(headline: str) -> str:
    """Classify news headline sentiment with negation-aware scoring."""
    hl = headline.lower()
    words = hl.replace("-", " ").split()
    word_set = set(words)
    
    # Negation words that flip the sentiment of nearby words
    negation_words = {"not", "no", "never", "none", "n't", "dont", "doesnt", "didnt", "wont", "wouldnt", "shouldnt", "cant", "cannot", "without", "lack", "lacking", "absence", "fails", "failed", "failing"}
    
    # Count positive/negative with negation awareness
    pos_count = 0
    neg_count = 0
    
    for i, w in enumerate(words):
        clean = w.strip(".,;:!?()[]{}\"'").replace("'", "")
        # Check if this word is negated (look back 1-3 words)
        is_negated = False
        if i > 0:
            for j in range(max(0, i-3), i):
                if words[j] in negation_words:
                    is_negated = True
                    break
        
        if clean in _POSITIVE_WORDS:
            if is_negated:
                neg_count += 1  # "not good" = negative
            else:
                pos_count += 1
        elif clean in _NEGATIVE_WORDS:
            if is_negated:
                pos_count += 0.5  # "not bad" = slightly positive
            else:
                neg_count += 1
    
    # Two-word phrases (stronger signals)
    pos_phrases = [
        "beats estimates","beats expectations","record profit","record revenue",
        "raises guidance","raises outlook","strong quarter","record quarter",
        "earnings beat","revenue beat","profit beat","sales beat",
        "buy rating","outperform rating","upgrade rating",
        "price target raised","target raised","pt raised",
        "undervalued","attractive valuation","compelling value",
        " defensive positioning","resilient earnings","solid quarter",
        "better than expected","above expectations","exceeded expectations",
    ]
    neg_phrases = [
        "misses estimates","misses expectations","cuts guidance","cuts outlook",
        "going concern","layoffs","job cuts","production halt","fails phase",
        "earnings miss","revenue miss","sales miss","profit miss",
        "guidance cut","forecast cut","outlook cut","revenue cut",
        "margin contraction","margin compress","margin pressure",
        "guidance lowered","outlook lowered","forecast lowered",
        "downgrade rating","sell rating","underweight rating",
        "price target cut","pt cut","target cut","target lowered",
        "worse than expected","below expectations","disappointing results",
        "warning sign","red flag","concern over","worried about",
        "production cut","supply chain","supply issue",
        "not good","not strong","not growing","not profitable",
        "lack of growth","lack of demand","weak demand","slowing growth",
        "slowing sales","declining revenue","falling margins",
        "debt concerns","leverage concerns","cash burn",
        "firing","laying off","job losses","departure of",
        "recession fears","inflation fears","tariff impact",
        "regulatory risk","regulatory hurdle","ban on",
        "abandons plan","cancels project","delays launch",
        "overvalued","expensive valuation","bubble risk",
        "bearish outlook","negative outlook","pessimistic outlook",
        "deteriorating fundamentals","weakening fundamentals",
    ]

    pos_phrase_score = sum(1 for p in pos_phrases if p in hl)
    neg_phrase_score = sum(1 for p in neg_phrases if p in hl)

    pos_count += pos_phrase_score * 2
    neg_count += neg_phrase_score * 2

    # Classification: require at least 1 net signal
    net = pos_count - neg_count
    if net >= 1:
        return "Positive"
    if net <= -1:
        return "Negative"
    return "Neutral"


_TICKER_MAP = {
    "apple":"AAPL","nvidia":"NVDA","microsoft":"MSFT","alphabet":"GOOGL","google":"GOOGL",
    "meta":"META","amazon":"AMZN","tsmc":"TSM","oracle":"ORCL","palantir":"PLTR",
    "reddit":"RDDT","goldman sachs":"GS","jpmorgan":"JPM","visa":"V","mastercard":"MA",
    "costco":"COST","walmart":"WMT","unitedhealth":"UNH","eli lilly":"LLY","abbvie":"ABBV",
    "advanced micro devices":"AMD","broadcom":"AVGO","crowdstrike":"CRWD",
    "servicenow":"NOW","snowflake":"SNOW","uber":"UBER","spotify":"SPOT",
    "netflix":"NFLX","disney":"DIS","bank of america":"BAC","tesla":"TSLA",
    "intel":"INTC","alibaba":"BABA","pfizer":"PFE","merck":"MRK","beyond meat":"BYND",
    "rivian":"RIVN","walgreens":"WBA","cvs":"CVS","nike":"NKE","starbucks":"SBUX",
    "snap":"SNAP","paypal":"PYPL","coinbase":"COIN","boeing":"BA","gamestop":"GME",
    "paramount":"PARA","doordash":"DASH","amc entertainment":"AMC","lucid":"LCID",
    "riot platforms":"RIOT","etsy":"ETSY","lyft":"LYFT","ford":"F","exxonmobil":"XOM",
    "chevron":"CVX","coca-cola":"KO","mcdonald":"MCD","general motors":"GM",
    "pepsico":"PEP","berkshire":"BRK","arm holdings":"ARM","warner bros":"WB",
    "jpmorgan chase":"JPM","goldman":"GS",
}

_ALL_TICKERS = [
    "AAPL","NVDA","MSFT","GOOGL","META","AMZN","TSM","TSMC","ORCL","PLTR",
    "RDDT","GS","JPM","V","MA","COST","WMT","UNH","LLY","ABBV","AMD","AVGO",
    "CRWD","NOW","SNOW","UBER","SPOT","NFLX","DIS","BAC","TSLA","INTC","BABA",
    "PFE","MRK","BYND","RIVN","WBA","CVS","NKE","SBUX","SNAP","PYPL","COIN",
    "BA","GME","PARA","DASH","AMC","LCID","RIOT","ETSY","LYFT","F","XOM","CVX",
    "KO","MCD","GM","PEP","BRK","ARM","ETSY","X","SPX","MU","BB","BX","IOT",
    "MRVL","SPCE","APPS","HIMX","ASTS","LASE","HUT","NBIS","LITE","NOW","OKLO",
    "PURR","RCAT","SPCX","TKO","USAR",
]


def _extract_ticker(headline: str) -> str | None:
    import re
    # 1. explicit $TICKER
    m = re.search(r'\$([A-Z]{1,5})', headline)
    if m:
        return m.group(1)
    # 2. standalone all-caps ticker in headline
    hl_upper = headline.upper()
    for tk in sorted(_ALL_TICKERS, key=len, reverse=True):
        if re.search(rf'\b{tk}\b', hl_upper):
            return tk
    # 3. company name lookup
    hl_lower = headline.lower()
    for name, tk in sorted(_TICKER_MAP.items(), key=lambda x: -len(x[0])):
        if name in hl_lower:
            return tk
    return None


@app.route("/internal/news/posts")
def news_posts():
    return jsonify(_news_posts)


@app.route("/internal/news/classify", methods=["POST"])
def classify_news():
    body = request.get_json(force=True)
    headline = body.get("headline", "").strip()
    if not headline:
        return jsonify({"error": "headline is required"}), 400
    ai_label = _classify_news_sentiment(headline)
    ai_ticker = _extract_ticker(headline)
    return jsonify({
        "ai_label": ai_label,
        "ai_ticker": ai_ticker,
    })


# ── Broad Market Sentiment (100 articles from ETFs + indices) ───────────────────

_BROAD_TICKERS = [
    "SPY","QQQ","IWM","DIA","TLT",
    "GLD","XLE","XLK","XLF","XLV",
    "XLY","XLRE","VXX","USO","VTI",
    "BTC-USD","^GSPC","^IXIC","^DJI","^VIX",
]

_BROAD_CACHE: dict = {"ts": 0, "data": None}
_BROAD_TTL = 1800    # 30 min — broad sentiment stays fresh


@app.route("/internal/market/broad-sentiment")
def broad_market_sentiment():
    import time as _time
    now = _time.time()
    if now - _BROAD_CACHE["ts"] < _BROAD_TTL and _BROAD_CACHE["data"]:
        return jsonify(_BROAD_CACHE["data"])

    all_articles: list = []
    results: list = [None] * len(_BROAD_TICKERS)

    def fetch_etf(i, tk):
        try:
            raw = _web_fetch_news(tk, limit=8)
            arts = []
            for item in raw:
                title = item.get("title", "").strip()
                if title:
                    arts.append({
                        "title": title,
                        "source": tk,
                        "label": _classify_news_sentiment(title),
                        "provider": item.get("provider", "Web"),
                        "url": item.get("url", ""),
                        "pub_date": item.get("pub_date", ""),
                    })
            results[i] = arts
        except Exception:
            results[i] = []

    threads = [threading.Thread(target=fetch_etf, args=(i, tk)) for i, tk in enumerate(_BROAD_TICKERS)]
    for th in threads: th.start()
    for th in threads: th.join(timeout=18)

    seen = set()
    for group in results:
        if group:
            for a in group:
                if a["title"] not in seen:
                    seen.add(a["title"])
                    all_articles.append(a)

    pos = sum(1 for a in all_articles if a["label"] == "Positive")
    neg = sum(1 for a in all_articles if a["label"] == "Negative")
    neu = sum(1 for a in all_articles if a["label"] == "Neutral")
    total = len(all_articles)
    # Score = positive share of opinionated articles (ignore neutral)
    opinionated = pos + neg or 1
    score = round(pos / opinionated * 100)

    data = {
        "score": score,
        "total_articles": total,
        "positive_count": pos,
        "negative_count": neg,
        "neutral_count": neu,
        "top_headlines": sorted(all_articles, key=lambda x: (0 if x["label"]=="Positive" else 1 if x["label"]=="Neutral" else 2)),
    }
    _BROAD_CACHE["ts"] = now
    _BROAD_CACHE["data"] = data
    return jsonify(data)


# ── Daily Stock Picks ───────────────────────────────────────────────────────────

# ── Dynamic Universe ────────────────────────────────────────────────────────────
# Hardcoded fallbacks used when web fetching fails.
_FALLBACK_LARGE = [
    "AAPL","MSFT","NVDA","GOOGL","META","AMZN","AVGO","TSLA","ORCL","TSM",
    "NOW","CRWD","PLTR","AMD","NET","DDOG","SHOP","TTD","ADBE","CRM","SNOW",
    "JPM","V","MA","BX","AXP","GS","KKR","SCHW","PYPL","ICE","CME",
    "LLY","ABBV","UNH","AMGN","ISRG","REGN","GILD","BSX","SYK",
    "COST","HD","MCD","CMG","NKE","SBUX","LULU","BKNG","ABNB",
    "XOM","CVX","CAT","GE","DE","NEE","OXY","FSLR","PWR",
    "RDDT","CELH","MARA","HIMS","RKLB","IONQ","SOFI",
    "MCO","SPGI","MSCI","CBOE","ANET","PANW","APP","FICO","FTNT",
    "ASML","NFLX","INTU","KLAC","ROP","MELI","SE","NU",
]
_FALLBACK_SMALL_MID = [
    "DUOL","CAVA","DXCM","WING","ELF","DECK","TMDX","PCOR",
    "APPF","AXON","ENPH","GNRC","MEDP","ODFL","PODD","UPST",
    "SMCI","SOUN","VRT","WFRD","CRDO","RXO","RVMD","TGTX",
]

_UNIVERSE_CACHE: dict = {"ts": 0.0, "large": [], "small_mid": []}
_UNIVERSE_TTL = 86_400  # 24 h — re-fetch ticker lists once per day

def _fetch_wiki_tickers(url: str, label: str) -> list:
    """Scrape ticker symbols from a Wikipedia stock-list page (wikitable, first column)."""
    import urllib.request, re
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8")

        # Primary: anchor inside first-column td  →  <td><a ...>AAPL</a></td>
        tickers = re.findall(
            r'<td[^>]*>\s*<a\s[^>]*>([A-Z]{1,5}(?:\.[A-Z]{1,2})?)</a>\s*</td>',
            html
        )
        # Secondary: bare td  →  <td>AAPL</td>
        if len(tickers) < 20:
            tickers = re.findall(r'<td>\s*([A-Z]{1,5})\s*</td>', html)

        # Normalise BRK.B → BRK-B and filter junk
        valid = []
        seen_local: set = set()
        for t in tickers:
            t = t.replace(".", "-")
            if re.match(r'^[A-Z]{1,5}(-[A-Z])?$', t) and t not in seen_local:
                seen_local.add(t)
                valid.append(t)

        app.logger.info(f"[universe] {label}: {len(valid)} tickers from {url}")
        return valid
    except Exception as e:
        app.logger.warning(f"[universe] {label} fetch failed: {e}")
        return []

def _get_universe() -> tuple:
    """Return (large_cap_list, small_mid_cap_list), refreshed once per day."""
    import time as _t
    now = _t.time()
    if now - _UNIVERSE_CACHE["ts"] < _UNIVERSE_TTL and len(_UNIVERSE_CACHE["large"]) >= 50:
        return _UNIVERSE_CACHE["large"], _UNIVERSE_CACHE["small_mid"]

    app.logger.info("[universe] Refreshing ticker universe from web...")

    # S&P 500  (~500 large-cap)
    sp500 = _fetch_wiki_tickers(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "S&P 500")
    # NASDAQ-100 (~100, mostly overlaps S&P 500 but adds some tech)
    ndx = _fetch_wiki_tickers(
        "https://en.wikipedia.org/wiki/Nasdaq-100", "NASDAQ-100")
    # S&P MidCap 400 (~400 mid-cap stocks)
    mid400 = _fetch_wiki_tickers(
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "S&P 400 Mid-Cap")
    # S&P SmallCap 600 (~600 small-cap stocks)
    small600 = _fetch_wiki_tickers(
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", "S&P 600 Small-Cap")

    # Build large-cap universe (S&P 500 + NASDAQ-100 extras)
    seen: set = set()
    large: list = []
    for t in sp500 + ndx:
        if t not in seen:
            seen.add(t)
            large.append(t)

    # Small/mid universe = S&P 400 mid + S&P 600 small, excluding large-cap
    seen_sm: set = set(large)
    small_mid: list = []
    for t in mid400 + small600:
        if t not in seen_sm:
            seen_sm.add(t)
            small_mid.append(t)

    # Fall back to hardcoded lists if fetching produced too little
    if len(large) < 50:
        app.logger.warning("[universe] Large-cap fetch insufficient — using fallback list")
        large = _FALLBACK_LARGE
    if len(small_mid) < 20:
        app.logger.warning("[universe] Small/mid fetch insufficient — using fallback list")
        small_mid = _FALLBACK_SMALL_MID

    _UNIVERSE_CACHE["ts"]        = now
    _UNIVERSE_CACHE["large"]     = large
    _UNIVERSE_CACHE["small_mid"] = small_mid
    app.logger.info(
        f"[universe] Ready: {len(large)} large-cap, {len(small_mid)} small/mid-cap"
    )
    return large, small_mid

# How many candidates to score each day from each universe
_PICKS_DAILY_SAMPLE     = 250  # score 250 → return top 10 (cast wide net)
_SPOTLIGHT_DAILY_SAMPLE = 50  # score 50 → return top 6

# _PICKS_POOL / _SMALL_MID_CAP_POOL are called inside the picks endpoint
# where shuffle is available; these shims are kept for the pre-warm path.
def _PICKS_POOL():
    large, _ = _get_universe()
    import random as _r, datetime as _dt
    seed = int(_dt.date.today().strftime("%Y%m%d")) + hash(str(large[0]) if large else "x")
    return _r.Random(seed).sample(large, min(_PICKS_DAILY_SAMPLE, len(large)))

def _SMALL_MID_CAP_POOL():
    _, sm = _get_universe()
    import random as _r, datetime as _dt
    seed = int(_dt.date.today().strftime("%Y%m%d")) + hash(str(sm[0]) if sm else "y") + 1
    return _r.Random(seed).sample(sm, min(_SPOTLIGHT_DAILY_SAMPLE, len(sm)))

_PICKS_CACHE: dict = {"ts": 0, "data": None}
_PICKS_TTL = 7200  # 2 hours — fresh picks pool twice daily


def _score_for_picks(info: dict) -> float:
    score = 0.0
    current = info.get("currentPrice") or info.get("regularMarketPrice")
    target = info.get("targetMeanPrice")

    # Analyst Upside (0-15 pts): need ~30% upside for max
    if target and current and current > 0:
        upside = (target - current) / current
        score += min(max(upside, 0) * 50, 15)

    # Analyst Consensus (0-20 pts): 1=Strong Buy → 5=Strong Sell
    rec = info.get("recommendationMean")
    if rec:
        score += max(0, (4.0 - rec) * 6.67)

    # Profit Margin (0-15 pts)
    pm = info.get("profitMargins")
    if pm and pm > 0:
        score += min(pm * 60, 15)

    # Revenue Growth (0-15 pts)
    rg = info.get("revenueGrowth")
    if rg and rg > 0:
        score += min(rg * 60, 15)

    # Valuation — P/E + EV/EBITDA (0-15 pts combined)
    pe = info.get("trailingPE")
    pe_pts = 0
    if pe and pe > 0:
        if pe <= 20:   pe_pts = 8
        elif pe <= 35: pe_pts = 5
        elif pe <= 55: pe_pts = 2
    ev_ebitda = info.get("enterpriseToEbitda")
    ev_pts = 0
    if ev_ebitda and ev_ebitda > 0:
        if ev_ebitda < 10:   ev_pts = 7
        elif ev_ebitda < 20: ev_pts = 4
        elif ev_ebitda < 35: ev_pts = 2
    score += pe_pts + ev_pts

    # Total Debt — D/E ratio (0-10 pts; web data returns value × 100)
    de = info.get("debtToEquity")
    if de is not None:
        if de < 50:    score += 10
        elif de < 100: score += 7
        elif de < 200: score += 4
        elif de < 350: score += 2

    # Free Cash Flow positive (0-10 pts)
    if (info.get("freeCashflow") or 0) > 0:
        score += 10

    # Dividend yield (0-5 pts) — reward steady income stocks
    dy = info.get("dividendYield")
    if dy is not None:
        if dy >= 0.03:     score += 5
        elif dy >= 0.02:   score += 3
        elif dy >= 0.01:   score += 1

    return round(score, 2)


def _load_picks_from_disk():
    """Load picks cache from disk so they survive deploys.
    Rejects stale-format files or data from a previous day.
    """
    import time, datetime as _dt
    try:
        if not _PICKS_DISK_PATH.exists():
            return
        with open(_PICKS_DISK_PATH) as f:
            blob = json.load(f)
        # --- Guard 1: stale TTL ---
        if time.time() - blob["ts"] >= _PICKS_TTL:
            print("[classifier_service] Disk cache expired (TTL).", flush=True)
            return
        # --- Guard 2: wrong date (previous day) ---
        today = _dt.date.today().isoformat()
        if blob.get("date") != today:
            print(f"[classifier_service] Disk cache stale (date mismatch).", flush=True)
            return
        # --- Guard 3: stale format (old schema without picks/spotlight/grades) ---
        data = blob.get("data")
        if not isinstance(data, dict):
            print("[classifier_service] Disk cache format mismatch (rejected).", flush=True)
            return
        if "picks" not in data or "spotlight" not in data or "grades" not in data:
            print("[classifier_service] Disk cache missing keys (rejected).", flush=True)
            return
        _PICKS_CACHE["ts"] = blob["ts"]
        _PICKS_CACHE["date"] = blob["date"]
        _PICKS_CACHE["shuffle"] = blob.get("shuffle", 0)
        _PICKS_CACHE["data"] = data
        print(f"[classifier_service] Restored picks from disk cache ({len(data.get('picks', []))} picks).", flush=True)
    except Exception as e:
        print(f"[classifier_service] picks disk load failed: {e}", flush=True)


def _load_detail_from_disk():
    """Load stock detail cache from disk so it survives deploys."""
    import time
    try:
        if _DETAIL_DISK_PATH.exists():
            with open(_DETAIL_DISK_PATH) as f:
                blob = json.load(f)
            for ticker, entry in blob.items():
                if time.time() - entry["ts"] < _DETAIL_CACHE_TTL:
                    _DETAIL_CACHE[ticker] = entry
            print(f"[classifier_service] Restored {_DETAIL_DISK_PATH} ({len(_DETAIL_CACHE)} tickers).", flush=True)
    except Exception as e:
        print(f"[classifier_service] detail disk load failed: {e}", flush=True)


def _save_detail_to_disk():
    """Save stock detail cache to disk."""
    try:
        with open(_DETAIL_DISK_PATH, "w") as f:
            json.dump(_DETAIL_CACHE, f)
    except Exception as e:
        print(f"[classifier_service] detail disk save failed: {e}", flush=True)


@app.route("/internal/stock/picks")
def stock_picks_endpoint():
    import time as _time, datetime as _dt
    now   = _time.time()
    today = _dt.date.today().isoformat()

    # Optional shuffle offset — when non-zero the user wants a fresh rotation
    shuffle = int(request.args.get("shuffle", 0))

    def _cache_is_fresh(entry: dict) -> bool:
        return (entry.get("data")
                and entry.get("date") == today
                and entry.get("shuffle", 0) == shuffle
                and now - entry.get("ts", 0) < _PICKS_TTL)

    if _cache_is_fresh(_PICKS_CACHE):
        return jsonify(_PICKS_CACHE["data"])
    # Fallback: disk cache — valid only for default (non-shuffled) requests today
    if shuffle == 0 and _PICKS_DISK_PATH.exists():
        try:
            with open(_PICKS_DISK_PATH) as f:
                blob = json.load(f)
            if _cache_is_fresh(blob):
                _PICKS_CACHE.update(blob)
                print("[classifier_service] Served picks from disk cache.", flush=True)
                return jsonify(blob["data"])
        except Exception:
            pass

    # Resolve today's rotated pools from the dynamic universe (shuffle shifts the seed)
    def _shuffled_pool(universe: list, n: int) -> list:
        import random as _random
        seed = int(today.replace("-", "")) + hash(str(universe[0]) if universe else "x") + shuffle * 9973
        rng  = _random.Random(seed)
        return rng.sample(universe, min(n, len(universe)))

    # Get dynamic universe from Wikipedia (refreshes daily)
    large, small_mid = _get_universe()
    today_pool    = _shuffled_pool(large,      _PICKS_DAILY_SAMPLE)
    today_sm_pool = _shuffled_pool(small_mid, _SPOTLIGHT_DAILY_SAMPLE)

    def _score_ticker(ticker: str) -> dict | None:
        """Score a single ticker using Finviz data (cached/fresh) or CSV fallback."""
        # Try live Finviz data first
        yf = _fetch_finviz(ticker)
        if yf:
            price = yf.get("currentPrice") or yf.get("regularMarketPrice")
            change_pct = _daily_change_from_chart(ticker) or yf.get("change_pct")
            market_cap = yf.get("marketCap")
            name = yf.get("name") or ticker
            sector = yf.get("sector") or "Unknown"
            pe = yf.get("trailingPE")
            profit_margin = yf.get("profitMargins")
            debt_to_equity = yf.get("debtToEquity")
            revenue_growth = yf.get("revenueGrowth")
            beta = yf.get("beta")
            cur_ratio = yf.get("currentRatio")
            target = yf.get("targetMeanPrice")
            forward_pe = yf.get("forwardPE")
            rec_key = yf.get("recommendationKey", "")
            analyst_count = yf.get("numberOfAnalystOpinions")
            if price:
                grade_s = _compute_grade_score(yf)
                grade = "A" if grade_s >= 75 else "B" if grade_s >= 60 else "C" if grade_s >= 45 else "D" if grade_s >= 30 else "F"
                pick_score = _score_for_picks(yf)
                if change_pct is not None:
                    pick_score += change_pct
                # Crash resilience
                crash_resilience = None
                if beta is not None and debt_to_equity is not None and cur_ratio is not None:
                    score_r = 0
                    if beta < 0.9:   score_r += 3
                    elif beta < 1.3: score_r += 2
                    elif beta < 1.8: score_r += 1
                    if debt_to_equity < 0.3:   score_r += 3
                    elif debt_to_equity < 0.8: score_r += 2
                    elif debt_to_equity < 1.5: score_r += 1
                    if cur_ratio >= 2.0:   score_r += 3
                    elif cur_ratio >= 1.2: score_r += 2
                    elif cur_ratio >= 0.8: score_r += 1
                    crash_resilience = "Strong" if score_r >= 7 else "Moderate" if score_r >= 5 else "Below Average" if score_r >= 3 else "Weak"
                # Upside
                upside_pct = None
                if target and price and price > 0:
                    upside_pct = round((target - price) / price * 100, 1)
                def _pct(v):
                    if v is None: return None
                    return f"{v*100:.1f}%"
                def _num(v, dec=2):
                    if v is None: return None
                    return f"{v:,.{dec}f}"
                return {
                    "ticker": ticker, "name": name, "sector": sector,
                    "industry": yf.get("industry", ""), "price": round(price, 2),
                    "change_pct": change_pct, "target": _num(target, 2) if target else None,
                    "upside_pct": upside_pct,
                    "analyst_count": int(analyst_count) if analyst_count else None,
                    "grade": grade, "grade_score": grade_s,
                    "pe": _num(pe, 1) if pe else None,
                    "forward_pe": _num(forward_pe, 1) if forward_pe else None,
                    "dividend_yield": _pct(yf.get("dividendYield")) if yf.get("dividendYield") is not None else "0.0%",
                    "profit_margin": _pct(profit_margin) if profit_margin is not None else None,
                    "debt_to_equity": _num(debt_to_equity, 2) if debt_to_equity else None,
                    "revenue_growth": _pct(revenue_growth) if revenue_growth is not None else None,
                    "market_cap": _fmt_big(market_cap),
                    "score": round(pick_score, 2),
                    "crash_resilience": crash_resilience,
                    "beta": _num(beta, 2) if beta else None,
                    "current_ratio": _num(cur_ratio, 2) if cur_ratio else None,
                }
        # Finviz failed or no price — try CSV fallback
        csv = _get_csv_stock_info(ticker)
        if csv and csv.get("current_price"):
            price = csv["current_price"]
            change_pct = csv.get("price_change_pct")
            market_cap = csv.get("market_cap")
            name = csv.get("name") or ticker
            sector = csv.get("sector") or "Unknown"
            # Simple grade from CSV data
            grade_s = 55
            if market_cap:
                if market_cap > 1e11: grade_s += 25
                elif market_cap > 1e10: grade_s += 15
            if change_pct is not None:
                if change_pct > 5: grade_s += 10
                elif change_pct < -5: grade_s -= 10
            grade_s = max(0, min(100, grade_s))
            grade = "A" if grade_s >= 75 else "B" if grade_s >= 60 else "C" if grade_s >= 45 else "D" if grade_s >= 30 else "F"
            # Simple score from CSV
            pick_score = grade_s * 0.5 + (change_pct or 0)
            return {
                "ticker": ticker, "name": name, "sector": sector,
                "industry": "", "price": round(price, 2),
                "change_pct": change_pct, "target": None,
                "upside_pct": None,
                "analyst_count": None,
                "grade": grade, "grade_score": grade_s,
                "pe": None, "forward_pe": None,
                "dividend_yield": "0.0%",
                "profit_margin": None,
                "debt_to_equity": None,
                "revenue_growth": None,
                "market_cap": _fmt_big(market_cap),
                "score": round(pick_score, 2),
                "crash_resilience": None,
                "beta": None,
                "current_ratio": None,
            }
        return None
    # Score all tickers sequentially (no Yahoo Finance = fast CSV lookup)
    scored: list = [None] * len(today_pool)
    scored_sm: list = [None] * len(today_sm_pool)
    for i, tk in enumerate(today_pool):
        scored[i] = _score_ticker(tk)
    for i, tk in enumerate(today_sm_pool):
        scored_sm[i] = _score_ticker(tk)

    valid = sorted([s for s in scored if s], key=lambda x: x["score"], reverse=True)
    valid_sm = sorted([s for s in scored_sm if s], key=lambda x: x["score"], reverse=True)

    # Only suggest C+ picks (grade_score >= 45) — never show D/F grades
    b_plus = [s for s in valid if s["grade_score"] >= 45]
    picks = b_plus[:10]  # may be fewer than 10 if the pool is thin

    # Small/mid cap spotlight: top 6 by score regardless of grade
    spotlight = valid_sm[:6]

    # Build a grade map for ALL pool stocks so the frontend can use
    # fundamentals scores on every chip, not just the top-10 picks.
    grades = {s["ticker"]: s["grade_score"] for s in (scored + scored_sm) if s}

    result = {"picks": picks, "spotlight": spotlight, "grades": grades}
    _PICKS_CACHE["ts"]      = now
    _PICKS_CACHE["date"]    = today
    _PICKS_CACHE["shuffle"] = shuffle
    _PICKS_CACHE["data"]    = result
    # Persist to disk only for the default (non-shuffled) request
    if shuffle == 0:
        try:
            with open(_PICKS_DISK_PATH, "w") as f:
                json.dump({"ts": now, "date": today, "shuffle": 0, "data": result}, f)
        except Exception as e:
            print(f"[classifier_service] picks disk save failed: {e}", flush=True)
    return jsonify(result)


# ── Stock Detail ────────────────────────────────────────────────────────────────

_DETAIL_CACHE: dict = {}
_DETAIL_CACHE_TTL = 3600    # 1 hour — stock detail stays current


def _compute_grade_score(info: dict) -> int:
    """0-100 composite fundamentals grade (aligned with pick-scoring philosophy)."""
    score = 0

    # P/E trailing — 0-15 pts (Valuation)
    pe = info.get("trailingPE")
    if pe and pe > 0:
        if pe <= 20:   score += 15
        elif pe <= 35: score += 10
        elif pe <= 55: score += 5
        else:          score += 1

    # EV/EBITDA — 0-10 pts (Valuation)
    ev_ebitda = info.get("enterpriseToEbitda")
    if ev_ebitda and ev_ebitda > 0:
        if ev_ebitda < 10:   score += 10
        elif ev_ebitda < 20: score += 6
        elif ev_ebitda < 35: score += 3

    # Debt/Equity — 0-10 pts (web returns value × 100)
    de = info.get("debtToEquity")
    if de is not None:
        if de < 50:    score += 10
        elif de < 100: score += 7
        elif de < 200: score += 4
        else:          score += 1

    # Free Cash Flow — 0-10 pts
    fcf = info.get("freeCashflow")
    if fcf is not None:
        score += 10 if fcf > 0 else 0

    # Profit Margin — 0-20 pts
    pm = info.get("profitMargins")
    if pm is not None:
        if pm >= 0.30:   score += 20
        elif pm >= 0.20: score += 15
        elif pm >= 0.10: score += 10
        elif pm >= 0:    score += 3

    # Revenue Growth — 0-15 pts
    rg = info.get("revenueGrowth")
    if rg is not None:
        if rg >= 0.20:   score += 15
        elif rg >= 0.10: score += 10
        elif rg >= 0.05: score += 6
        elif rg >= 0:    score += 2

    # Analyst Recommendation — 0-20 pts (1=Strong Buy, 5=Strong Sell)
    rec = info.get("recommendationMean")
    if rec is not None:
        if rec <= 1.5:   score += 20
        elif rec <= 2.0: score += 15
        elif rec <= 2.5: score += 10
        elif rec <= 3.0: score += 5
        else:            score += 1

    # Dividend yield — 0-5 pts
    dy = info.get("dividendYield")
    if dy is not None:
        if dy >= 0.03:     score += 5
        elif dy >= 0.02:   score += 3
        elif dy >= 0.01:   score += 1

    return min(100, score)


def _fmt_big(n):
    """Format large number as $1.2T / $800B / $45M."""
    if n is None: return None
    if abs(n) >= 1e12: return f"${n/1e12:.2f}T"
    if abs(n) >= 1e9:  return f"${n/1e9:.1f}B"
    if abs(n) >= 1e6:  return f"${n/1e6:.1f}M"
    return f"${n:.0f}"


# Common ticker aliases for misspellings
_TICKER_ALIASES = {
    "APPL": "AAPL",   # Apple (misspelling)
    "FB":   "META",   # Facebook
    "BRKB": "BRK-B",  # Berkshire Hathaway
    "BRK.B": "BRK-B", # Berkshire dot variant
    "GOOG": "GOOGL",  # Google (class A)
    "BERK": "BRK-B",  # Berkshire
    "BERKSHIRE": "BRK-B",
}

@app.route("/internal/stock/detail/<ticker>")
def stock_detail(ticker: str):
    """Stock detail — live Finviz data for any ticker."""
    tk = _TICKER_ALIASES.get(ticker.upper().replace(".", "-"), ticker.upper().replace(".", "-"))

    # Fetch live data from Finviz
    yf = _fetch_finviz(tk)
    if yf:
        price = yf.get("currentPrice") or yf.get("regularMarketPrice") or 0
        change_pct = _daily_change_from_chart(tk) or yf.get("change_pct")
        name = yf.get("name") or tk
        market_cap = yf.get("marketCap")
        w52_low = yf.get("fiftyTwoWeekLow")
        w52_high = yf.get("fiftyTwoWeekHigh")
        sector = yf.get("sector") or "Unknown"
    else:
        # Fallback to CSV data for the detail page
        csv = _get_csv_stock_info(tk)
        if csv:
            price = csv.get("current_price") or 0
            change_pct = csv.get("price_change_pct")
            name = csv.get("name") or tk
            market_cap = csv.get("market_cap")
            sector = csv.get("sector") or "Unknown"
        else:
            price = 0
            change_pct = None
            name = tk
            market_cap = None
            sector = "Unknown"
        w52_low = None
        w52_high = None

    # Grade from Finviz if available, else CSV fallback
    grade_s = _compute_grade_score(yf or {})
    if not yf and market_cap:
        # Simple grade from CSV data
        grade_s = 55
        if market_cap:
            if market_cap > 1e11: grade_s += 25
            elif market_cap > 1e10: grade_s += 15
        if change_pct is not None:
            if change_pct > 5: grade_s += 10
            elif change_pct < -5: grade_s -= 10
        grade_s = max(0, min(100, grade_s))
    grade = "A" if grade_s >= 75 else "B" if grade_s >= 60 else "C" if grade_s >= 45 else "D" if grade_s >= 30 else "F"

    # Format values
    def _pct(v):
        if v is None: return None
        return f"{v*100:.1f}%"
    def _num(v, dec=2):
        if v is None: return None
        return f"{v:,.{dec}f}"
    def _rec(v):
        if v is None: return None
        return "Strong Buy" if v <= 1.5 else "Buy" if v <= 2.0 else "Hold" if v <= 2.5 else "Sell" if v <= 3.5 else "Strong Sell"

    # Real metrics from Finviz (keys match the yfinance-like schema)
    metrics = {
        "market_cap": _fmt_big(market_cap),
        "sector": sector,
        "total_equity": None,
        "total_debt": _fmt_big(yf.get("totalDebt")) if yf else None,
        "enterprise_value": _fmt_big(yf.get("enterpriseValue")) if yf else None,
        "pe_trailing": _num(yf.get("trailingPE"), 1) if yf else None,
        "pe_forward": _num(yf.get("forwardPE"), 1) if yf else None,
        "price_to_book": _num(yf.get("priceToBook"), 2) if yf else None,
        "eps": _num(yf.get("trailingEps"), 2) if yf else None,
        "dividend_yield": _pct(yf.get("dividendYield")) if yf else None,
        "profit_margin": _pct(yf.get("profitMargins")) if yf else None,
        "revenue_growth": _pct(yf.get("revenueGrowth")) if yf else None,
        "debt_to_equity": _num(yf.get("debtToEquity"), 2) if yf else None,
        "current_ratio": _num(yf.get("currentRatio"), 2) if yf else None,
        "quick_ratio": _num(yf.get("quickRatio"), 2) if yf else None,
        "roe": _pct(yf.get("returnOnEquity")) if yf else None,
        "roa": _pct(yf.get("returnOnAssets")) if yf else None,
        "beta": _num(yf.get("beta"), 2) if yf else None,
        "operating_margin": _pct(yf.get("operatingMargins")) if yf else None,
        "op_cash_flow": None,
        "free_cash_flow": _fmt_big(yf.get("freeCashflow")) if yf else None,
        "earnings_growth": _pct(yf.get("earningsGrowth")) if yf else None,
        "52w_high": w52_high,
        "52w_low": w52_low,
        "analyst_target": _num(yf.get("targetMeanPrice"), 2) if yf else None,
        "analyst_rec": _rec(yf.get("recommendationMean")) if yf else None,
        "analyst_count": None,
        "crash_resilience": None,
    }

    # Compute crash resilience from available data
    if yf:
        beta = yf.get("beta")
        de = yf.get("debtToEquity")
        cur = yf.get("currentRatio")
        if beta is not None and de is not None and cur is not None:
            score_r = 0
            if beta < 0.9:   score_r += 3
            elif beta < 1.3: score_r += 2
            elif beta < 1.8: score_r += 1
            if de < 0.3:   score_r += 3
            elif de < 0.8: score_r += 2
            elif de < 1.5: score_r += 1
            if cur >= 2.0:   score_r += 3
            elif cur >= 1.2: score_r += 2
            elif cur >= 0.8: score_r += 1
            metrics["crash_resilience"] = "Strong" if score_r >= 7 else "Moderate" if score_r >= 5 else "Below Average" if score_r >= 3 else "Weak"

    # Real chart from Yahoo Finance (with fallback to hourly for missing daily closes)
    chart = _fetch_yahoo_chart_filled(tk)
    if not chart:
        # Dynamic synthetic fallback based on today's date
        chart = []
        if price:
            today = datetime.now().date()
            # Generate 5 evenly spaced points over the last 30 days
            for days_ago in [30, 22, 14, 7, 0]:
                d = today - timedelta(days=days_ago)
                # Slight random variation around current price
                variation = 1 + (0.05 * (days_ago / 30) * (-1 if days_ago % 2 == 0 else 1))
                chart.append({"date": d.strftime("%Y-%m-%d"), "close": round(price * variation, 2)})

    result = {
        "ticker": tk,
        "name": name,
        "sector": sector,
        "industry": (yf.get("industry") if yf else "") or "",
        "price": price,
        "change_pct": change_pct,
        "market_cap": _fmt_big(market_cap),
        "week52_low": w52_low,
        "week52_high": w52_high,
        "ipo": (yf.get("ipo") if yf else None) or None,
        "chart": chart,
        "grade": grade,
        "grade_score": grade_s,
        "metrics": metrics,
    }

    return jsonify(result)
def _prewarm_universe_cache():
    """Fetch Finviz data for every ticker in the universe in the background.
    This ensures any shuffle seed hits warm cache data instead of making live requests."""
    import time as _t
    _t.sleep(10)  # wait for picks prewarm to finish first
    print("[classifier_service] Pre-loading Finviz cache for full universe...", flush=True)
    try:
        large, small_mid = _get_universe()
        all_tickers = list(dict.fromkeys(large + small_mid))  # dedupe, preserve order
        loaded = 0
        for tk in all_tickers:
            try:
                cached = _STOCK_CACHE.get(tk)
                now = _t.time()
                if cached and now - cached.get("ts", 0) < _STOCK_CACHE_TTL:
                    loaded += 1
                    continue  # already warm
                _fetch_finviz(tk)
                loaded += 1
                _t.sleep(0.15)  # gentle rate limiting
            except Exception:
                pass
        print(f"[classifier_service] Universe cache warm ({loaded}/{len(all_tickers)} tickers).", flush=True)
    except Exception as e:
        print(f"[classifier_service] Universe prewarm failed: {e}", flush=True)


def _prewarm_picks():
    """Score all picks pools at startup so the first user request hits cache.
    If disk cache is fresh and valid, skip the expensive work entirely.
    If stale or invalid, forces a full rebuild so the app never serves stale data.
    """
    import time as _t, datetime as _dt
    _t.sleep(3)  # let Flask finish starting up first
    _load_picks_from_disk()
    _load_detail_from_disk()  # also restore stock detail cache
    if _PICKS_CACHE["data"]:
        print("[classifier_service] Picks loaded from disk — skipping pre-warm.", flush=True)
        return
    # Force-delete any stale disk cache so it never resurrects on next deploy
    try:
        if _PICKS_DISK_PATH.exists():
            _PICKS_DISK_PATH.unlink()
            print("[classifier_service] Deleted stale picks cache.", flush=True)
        if _DETAIL_DISK_PATH.exists():
            _DETAIL_DISK_PATH.unlink()
            print("[classifier_service] Deleted stale detail cache.", flush=True)
    except Exception:
        pass
    print("[classifier_service] Pre-warming picks cache in background...", flush=True)
    try:
        with app.test_client() as c:
            c.get("/internal/stock/picks")
        print("[classifier_service] Picks cache warm.", flush=True)
    except Exception as e:
        print(f"[classifier_service] Pre-warm failed: {e}", flush=True)


def _hourly_snapshot_worker():
    """Run every 2 hours to take snapshots of all tickers.
    Reduced from 1h to 2h to minimize Finviz rate-limit risk
    while still keeping data reasonably fresh for 2-person usage."""
    import time as _t
    _t.sleep(120)  # wait 2 minutes after startup
    while True:
        try:
            _take_hourly_snapshots()
        except Exception as e:
            print(f"[hourly_worker] Error: {e}", flush=True)
        _t.sleep(7200)  # sleep 2 hours


def _daily_refresh_worker():
    """Run every 6 hours to clear in-memory caches so data stays fresh.
    Full picks pool rescored daily (at midnight UTC) to catch new tickers.
    """
    import time as _t, datetime as _dt
    _t.sleep(120)  # wait 2 minutes after startup
    while True:
        try:
            now = _dt.datetime.now()
            # --- At midnight: full daily rebuild ---
            if now.hour == 0 and now.minute < 10:
                print(f"[daily_refresh] {now.isoformat()} — Daily full rebuild", flush=True)
                # Clear all caches
                _BROAD_CACHE["ts"] = 0; _BROAD_CACHE["data"] = None
                _WEB_CACHE.clear()
                _UNIVERSE_CACHE["ts"] = 0
                _PICKS_CACHE["ts"] = 0; _PICKS_CACHE["data"] = None
                _DETAIL_CACHE.clear()
                # Delete disk caches so they don't resurrect stale data
                try:
                    if _PICKS_DISK_PATH.exists(): _PICKS_DISK_PATH.unlink()
                    if _DETAIL_DISK_PATH.exists(): _DETAIL_DISK_PATH.unlink()
                except Exception:
                    pass
                # Force fresh universe + picks
                _get_universe()
                with app.test_client() as c:
                    c.get("/internal/stock/picks")
                print("[daily_refresh] Daily rebuild complete.", flush=True)
            # --- Every 6 hours: clear sentiment caches ---
            else:
                print(f"[daily_refresh] {now.isoformat()} — Clearing sentiment caches", flush=True)
                _BROAD_CACHE["ts"] = 0; _BROAD_CACHE["data"] = None
                _WEB_CACHE.clear()
                print("[daily_refresh] Sentiment caches cleared.", flush=True)
        except Exception as e:
            print(f"[daily_refresh] Error: {e}", flush=True)
        # Sleep until next 6-hour boundary (00:00, 06:00, 12:00, 18:00)
        _t.sleep(21600)  # 6 hours


if __name__ == "__main__":
    port = int(os.environ.get("PYTHON_SERVICE_PORT", 5100))
    print(f"[classifier_service] Starting on port {port}", flush=True)
    threading.Thread(target=_prewarm_picks, daemon=True).start()
    threading.Thread(target=_prewarm_universe_cache, daemon=True).start()
    threading.Thread(target=_hourly_snapshot_worker, daemon=True).start()
    threading.Thread(target=_daily_refresh_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)
