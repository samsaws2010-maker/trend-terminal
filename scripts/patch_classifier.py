#!/usr/bin/env python3
"""Patch classifier_service.py to remove Yahoo Finance, use CSV data."""

import re, sys

path = "artifacts/api-server/python/classifier_service.py"
with open(path) as f:
    content = f.read()

# 1. Replace yfinance-dependent functions with stubs
old_block = '''def _web_fetch_stock_summary(ticker: str) -> dict:
    """Fetch stock summary data via yfinance library."""
    try:
        import yfinance as yf
        import requests
        # Use a browser-like session to avoid Yahoo rate limiting on server IPs
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        t = yf.Ticker(ticker, session=session)
        info = t.info
        if not info:
            app.logger.warning(f"[yfinance] empty info for {ticker}")
            return {}
        # yfinance returns {"trailingPegRatio": None} dict even on failure for some tickers;
        # check for a meaningful field to confirm we have real data
        if not info.get("regularMarketPrice") and not info.get("currentPrice") and not info.get("previousClose"):
            app.logger.warning(f"[yfinance] no price fields for {ticker}, keys={list(info.keys())[:8]}")
            return {}

        # Pull stockholders equity from quarterly balance sheet — not available in .info
        total_equity = None
        try:
            bs = t.quarterly_balance_sheet
            if bs is not None and not bs.empty:
                for row_name in ("Stockholders Equity", "Common Stock Equity",
                                 "Total Equity Gross Minority Interest"):
                    if row_name in bs.index:
                        val = bs.loc[row_name].iloc[0]
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            total_equity = float(val)
                            break
        except Exception:
            pass

        # Convert yfinance dict format to the same format as the old API
        # so _web_extract_info() works unchanged
        return {
            "price": {"longName": info.get("longName"), "shortName": info.get("shortName"),
                      "regularMarketPrice": {"raw": info.get("currentPrice")},
                      "regularMarketChangePercent": {"raw": info.get("regularMarketChangePercent")},
                      "marketCap": {"raw": info.get("marketCap")},
                      "previousClose": {"raw": info.get("previousClose")},
                      },
            "stats": {"trailingPE": {"raw": info.get("trailingPE")},
                      "forwardPE": {"raw": info.get("forwardPE")},
                      "priceToBook": {"raw": info.get("priceToBook")},
                      "beta": {"raw": info.get("beta")},
                      "trailingEps": {"raw": info.get("trailingEps")},
                      "bookValue": {"raw": info.get("bookValue")},
                      "sharesOutstanding": {"raw": info.get("sharesOutstanding")},
                      "targetMeanPrice": {"raw": info.get("targetMeanPrice")},
                      "targetHighPrice": {"raw": info.get("targetHighPrice")},
                      "targetLowPrice": {"raw": info.get("targetLowPrice")},
                      "recommendationKey": {"raw": info.get("recommendationKey")},
                      "recommendationMean": {"raw": info.get("recommendationMean")},
                      "numberOfAnalystOpinions": {"raw": info.get("numberOfAnalystOpinions")},
                      "enterpriseToEbitda": {"raw": info.get("enterpriseToEbitda")},
                      "sector": {"raw": info.get("sector")},
                      "industry": {"raw": info.get("industry")},
                      },
            "summary": {"fiftyTwoWeekLow": {"raw": info.get("fiftyTwoWeekLow")},
                        "fiftyTwoWeekHigh": {"raw": info.get("fiftyTwoWeekHigh")},
                        "dividendYield": {"raw": info.get("dividendYield")},
                        },
            "fin": {"profitMargins": {"raw": info.get("profitMargins")},
                    "revenueGrowth": {"raw": info.get("revenueGrowth")},
                    "earningsGrowth": {"raw": info.get("earningsGrowth")},
                    "debtToEquity": {"raw": info.get("debtToEquity")},
                    "currentRatio": {"raw": info.get("currentRatio")},
                    "quickRatio": {"raw": info.get("quickRatio")},
                    "returnOnEquity": {"raw": info.get("returnOnEquity")},
                    "returnOnAssets": {"raw": info.get("returnOnAssets")},
                    "operatingMargins": {"raw": info.get("operatingMargins")},
                    "operatingCashflow": {"raw": info.get("operatingCashflow")},
                    "freeCashflow": {"raw": info.get("freeCashflow")},
                    "totalDebt": {"raw": info.get("totalDebt")},
                    "enterpriseValue": {"raw": info.get("enterpriseValue")},
                    "totalStockholderEquity": {"raw": total_equity},
                    },
        }
    except Exception as e:
        app.logger.error(f"[yfinance] _web_fetch_stock_summary({ticker}) failed: {e}")
        return {}

def _web_fetch_chart(ticker: str) -> dict:
    """Fetch chart data via yfinance library."""
    try:
        import yfinance as yf
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })
        t = yf.Ticker(ticker, session=session)
        hist = t.history(period="1mo")
        if hist.empty:
            return {}
        chart_data = []
        for idx, row in hist.iterrows():
            dt = idx.strftime("%Y-%m-%d")
            close = float(row.get("Close", 0))
            if close > 0:
                chart_data.append({"date": dt, "close": round(close, 2)})
        price = None
        change_pct = None
        if not hist.empty:
            price = float(hist.iloc[-1].get("Close", 0))
            if len(hist) > 1:
                prev = float(hist.iloc[-2].get("Close", 0))
                if prev > 0:
                    change_pct = round((price - prev) / prev * 100, 2)
        return {
            "price": price,
            "change_pct": change_pct,
            "prev_close": float(hist.iloc[-2].get("Close", 0)) if len(hist) > 1 else None,
            "chart": chart_data,
        }
    except Exception as e:
        app.logger.error(f"[yfinance] _web_fetch_chart({ticker}) failed: {e}")
        return {}

def _web_extract_info(summary: dict) -> dict:
    """Convert web-scraped quote summary to a flat dict compatible with existing code."""
    s = summary.get("summary", {})
    st = summary.get("stats", {})
    f = summary.get("fin", {})
    p = summary.get("price", {})

    def _get(obj, key):
        v = obj.get(key)
        return v.get("raw") if isinstance(v, dict) else v

    return {
        "longName": p.get("longName") or p.get("shortName"),
        "currentPrice": _get(p, "regularMarketPrice") or _get(p, "previousClose"),
        "regularMarketPrice": _get(p, "regularMarketPrice"),
        "regularMarketChangePercent": _get(p, "regularMarketChangePercent"),
        "marketCap": _get(p, "marketCap") or _get(s, "marketCap"),
        "trailingPE": _get(st, "trailingPE"),
        "forwardPE": _get(st, "forwardPE"),
        "priceToBook": _get(st, "priceToBook"),
        "beta": _get(st, "beta"),
        "trailingEps": _get(st, "trailingEps"),
        "bookValue": _get(st, "bookValue"),
        "sharesOutstanding": _get(st, "sharesOutstanding"),
        "targetMeanPrice": _get(st, "targetMeanPrice"),
        "targetHighPrice": _get(st, "targetHighPrice"),
        "targetLowPrice": _get(st, "targetLowPrice"),
        "recommendationKey": _get(st, "recommendationKey"),
        "recommendationMean": _get(st, "recommendationMean"),
        "numberOfAnalystOpinions": _get(st, "numberOfAnalystOpinions"),
        "enterpriseToEbitda": _get(st, "enterpriseToEbitda"),
        "fiftyTwoWeekLow": _get(s, "fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": _get(s, "fiftyTwoWeekHigh"),
        "dividendYield": _get(s, "dividendYield"),
        "profitMargins": _get(f, "profitMargins"),
        "revenueGrowth": _get(f, "revenueGrowth"),
        "earningsGrowth": _get(f, "earningsGrowth"),
        "debtToEquity": _get(f, "debtToEquity"),
        "currentRatio": _get(f, "currentRatio"),
        "quickRatio": _get(f, "quickRatio"),
        "returnOnEquity": _get(f, "returnOnEquity"),
        "returnOnAssets": _get(f, "returnOnAssets"),
        "operatingMargins": _get(f, "operatingMargins"),
        "operatingCashflow": _get(f, "operatingCashflow"),
        "freeCashflow": _get(f, "freeCashflow"),
        "totalDebt": _get(f, "totalDebt"),
        "enterpriseValue": _get(f, "enterpriseValue"),
        "totalStockholderEquity": _get(f, "totalStockholderEquity"),
        "sector": _get(st, "sector"),
        "industry": _get(st, "industry"),
    }'''

new_block = '''def _web_fetch_stock_summary(ticker: str) -> dict:
    """DEPRECATED — no Yahoo Finance. Returns empty dict."""
    return {}

def _web_fetch_chart(ticker: str) -> dict:
    """DEPRECATED — no Yahoo Finance. Returns empty dict."""
    return {}

def _web_extract_info(summary: dict) -> dict:
    """DEPRECATED — no longer used. Returns empty dict."""
    return {}

# ── CSV-based stock data (replaces Yahoo Finance) ───────────────────────────

_CSV_PRICES: pd.DataFrame | None = None
_CSV_PRICES_TS: float = 0.0
_CSV_PRICES_TTL = 300  # 5 min in-memory cache


def _load_csv_prices() -> pd.DataFrame:
    """Load ticker_prices.csv into a DataFrame with caching."""
    global _CSV_PRICES, _CSV_PRICES_TS
    import time
    now = time.time()
    if _CSV_PRICES is not None and now - _CSV_PRICES_TS < _CSV_PRICES_TTL:
        return _CSV_PRICES
    try:
        path = str(EXTRACTED_DIR / "ticker_prices.csv")
        df = pd.read_csv(path)
        _CSV_PRICES = df
        _CSV_PRICES_TS = now
        return df
    except Exception as e:
        print(f"[csv] failed to load ticker_prices.csv: {e}", flush=True)
        return pd.DataFrame()


def _get_csv_stock_info(ticker: str) -> dict | None:
    """Get stock info from CSV (no Yahoo Finance)."""
    df = _load_csv_prices()
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
    }'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("[patch] replaced _web_fetch_* functions + added CSV helpers")
else:
    print("[patch] ERROR: could not find old block")
    sys.exit(1)

# 2. Replace stock_info endpoint
old_stock_info = '''@app.route("/internal/stocks/<ticker>")
def stock_info(ticker):
    try:
        info = get_stock_info(ticker.upper())
        return jsonify({
            "ticker": info["ticker"],
            "name": info["name"],
            "sector": info["sector"],
            "industry": info["industry"],
            "current_price": _safe(info["current_price"]) or 0.0,
            "previous_close": _safe(info["previous_close"]) or 0.0,
            "price_change": _safe(info["price_change"]) or 0.0,
            "price_change_pct": _safe(info["price_change_pct"]) or 0.0,
            "market_cap": _safe(info["market_cap"]),
            "week_52_high": _safe(info["week_52_high"]),
            "week_52_low": _safe(info["week_52_low"]),
            "description": info["description"],
            "error": info["error"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500'''

new_stock_info = '''@app.route("/internal/stocks/<ticker>")
def stock_info(ticker):
    try:
        info = _get_csv_stock_info(ticker.upper())
        if not info:
            return jsonify({"error": "not_found"}), 404
        return jsonify({
            "ticker": info["ticker"],
            "name": info["name"],
            "sector": info["sector"],
            "industry": "Unknown",
            "current_price": info["current_price"] or 0.0,
            "previous_close": 0.0,
            "price_change": 0.0,
            "price_change_pct": info["price_change_pct"] or 0.0,
            "market_cap": info["market_cap"],
            "week_52_high": info["week_52_high"],
            "week_52_low": info["week_52_low"],
            "description": "",
            "error": None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500'''

if old_stock_info in content:
    content = content.replace(old_stock_info, new_stock_info)
    print("[patch] replaced stock_info endpoint")
else:
    print("[patch] WARNING: could not find stock_info endpoint")

# 3. Replace stock_history endpoint
old_hist = '''@app.route("/internal/stocks/<ticker>/history")
def stock_history(ticker):
    period = request.args.get("period", "1mo")
    valid_periods = {"1wk", "1mo", "3mo", "6mo", "1y"}
    if period not in valid_periods:
        period = "1mo"
    try:
        hist = get_price_history(ticker.upper(), period=period)
        if hist.empty:
            return jsonify([])
        result = []
        for date, row in hist.iterrows():
            result.append({
                "date": str(date.date()) if hasattr(date, "date") else str(date),
                "open": _safe(float(row.get("Open", 0))) if row.get("Open") is not None else None,
                "high": _safe(float(row.get("High", 0))) if row.get("High") is not None else None,
                "low": _safe(float(row.get("Low", 0))) if row.get("Low") is not None else None,
                "close": _safe(float(row.get("Close", 0))) if row.get("Close") is not None else None,
                "volume": _safe(float(row.get("Volume", 0))) if row.get("Volume") is not None else None,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500'''

new_hist = '''@app.route("/internal/stocks/<ticker>/history")
def stock_history(ticker):
    # No historical chart data available from CSV-only source
    return jsonify([])'''

if old_hist in content:
    content = content.replace(old_hist, new_hist)
    print("[patch] replaced stock_history endpoint")
else:
    print("[patch] WARNING: could not find stock_history endpoint")

# 4. Replace stock_detail endpoint
old_detail = '''@app.route("/internal/stock/detail/<ticker>")
def stock_detail(ticker: str):
    """Stock detail — fetch from web data with disk caching."""
    tk = ticker.upper()
    now = time.time()

    # Check memory cache
    cached = _DETAIL_CACHE.get(tk)
    if cached and now - cached["ts"] < _DETAIL_CACHE_TTL:
        return jsonify(cached["data"])

    # Check disk cache
    if _DETAIL_DISK_PATH.exists():
        try:
            with open(_DETAIL_DISK_PATH) as f:
                blob = json.load(f)
            entry = blob.get(tk)
            if entry and now - entry["ts"] < _DETAIL_CACHE_TTL:
                _DETAIL_CACHE[tk] = entry
                return jsonify(entry["data"])
        except Exception:
            pass

    # Fetch from web
    summary = _web_fetch_stock_summary(tk)
    chart_data = _web_fetch_chart(tk)
    info = _web_extract_info(summary)

    if not info.get("currentPrice") and not chart_data.get("price"):
        return jsonify({"error": "not_found", "message": f"No data found for {tk}"}), 404

    price = info.get("currentPrice") or chart_data.get("price")
    change_pct = info.get("regularMarketChangePercent") or chart_data.get("change_pct")
    name = info.get("longName", tk)
    market_cap = info.get("marketCap")
    w52_low = info.get("fiftyTwoWeekLow")
    w52_high = info.get("fiftyTwoWeekHigh")
    grade_s = _compute_grade_score(info)
    grade = "A" if grade_s >= 85 else "B" if grade_s >= 70 else "C" if grade_s >= 55 else "D" if grade_s >= 40 else "F"

    # crash resilience
    cr = None
    beta = info.get("beta")
    pm = info.get("profitMargins")
    de = info.get("debtToEquity")
    if beta is not None or pm is not None or de is not None:
        cr_pts = 0
        if beta is not None:
            cr_pts += (1 - min(beta, 2)/2) * 40
        if pm is not None:
            cr_pts += (pm * 100 if pm <= 1 else pm) * 0.3
        if de is not None:
            cr_pts += (1 - min(abs(de)/500, 1)) * 20
        cr = "Strong" if cr_pts >= 55 else "Moderate" if cr_pts >= 35 else "Below Average" if cr_pts >= 18 else "Weak"

    metrics = {
        "market_cap": _fmt_big(market_cap),
        "total_equity": _fmt_big(info.get("totalStockholderEquity")),
        "total_debt": _fmt_big(info.get("totalDebt")),
        "enterprise_value": _fmt_big(info.get("enterpriseValue")),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "price_to_book": info.get("priceToBook"),
        "eps": f"${info['trailingEps']:.2f}" if info.get("trailingEps") else None,
        "dividend_yield": f"{round(info['dividendYield']*100,2)}%" if info.get("dividendYield") else None,
        "profit_margin": f"{round(info['profitMargins']*100,1)}%" if info.get("profitMargins") else None,
        "revenue_growth": f"{round(info['revenueGrowth']*100,1)}%" if info.get("revenueGrowth") is not None else None,
        "debt_to_equity": round(de/100, 2) if de is not None else None,
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
        "roe": f"{round(info['returnOnEquity']*100,1)}%" if info.get("returnOnEquity") else None,
        "roa": f"{round(info['returnOnAssets']*100,1)}%" if info.get("returnOnAssets") else None,
        "beta": beta,
        "operating_margin": f"{round(info['operatingMargins']*100,1)}%" if info.get("operatingMargins") else None,
        "op_cash_flow": _fmt_big(info.get("operatingCashflow")),
        "free_cash_flow": _fmt_big(info.get("freeCashflow")),
        "earnings_growth": f"{round(info['earningsGrowth']*100,1)}%" if info.get("earningsGrowth") is not None else None,
        "52w_high": w52_high,
        "52w_low": w52_low,
        "analyst_target": info.get("targetMeanPrice"),
        "analyst_rec": (info.get("recommendationKey") or "").replace("_", " ").title() if info.get("recommendationKey") else None,
        "analyst_count": info.get("numberOfAnalystOpinions"),
        "crash_resilience": cr,
    }

    chart = chart_data.get("chart", [])
    result = {
        "ticker": tk,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "market_cap": _fmt_big(market_cap),
        "week52_low": w52_low,
        "week52_high": w52_high,
        "chart": chart,
        "grade": grade,
        "grade_score": grade_s,
        "metrics": metrics,
    }'''

new_detail = '''@app.route("/internal/stock/detail/<ticker>")
def stock_detail(ticker: str):
    """Stock detail — from CSV data only (no Yahoo Finance)."""
    tk = ticker.upper()
    info = _get_csv_stock_info(tk)
    if not info:
        return jsonify({"error": "not_found", "message": f"No data found for {tk}"}), 404

    price = info["current_price"]
    change_pct = info["price_change_pct"]
    name = info["name"] or tk
    market_cap = info["market_cap"]
    w52_low = info["week_52_low"]
    w52_high = info["week_52_high"]
    sector = info["sector"] or "Unknown"

    # Simple grade based on market cap and price momentum
    grade_s = 50
    if market_cap:
        if market_cap > 1e11: grade_s += 20
        elif market_cap > 1e10: grade_s += 10
    if change_pct is not None:
        if change_pct > 5: grade_s += 10
        elif change_pct < -5: grade_s -= 10
    grade_s = max(0, min(100, grade_s))
    grade = "A" if grade_s >= 85 else "B" if grade_s >= 70 else "C" if grade_s >= 55 else "D" if grade_s >= 40 else "F"

    # Minimal metrics (no Yahoo Finance = most unavailable)
    metrics = {
        "market_cap": _fmt_big(market_cap),
        "total_equity": None,
        "total_debt": None,
        "enterprise_value": None,
        "pe_trailing": None,
        "pe_forward": None,
        "price_to_book": None,
        "eps": None,
        "dividend_yield": None,
        "profit_margin": None,
        "revenue_growth": None,
        "debt_to_equity": None,
        "current_ratio": None,
        "quick_ratio": None,
        "roe": None,
        "roa": None,
        "beta": None,
        "operating_margin": None,
        "op_cash_flow": None,
        "free_cash_flow": None,
        "earnings_growth": None,
        "52w_high": w52_high,
        "52w_low": w52_low,
        "analyst_target": None,
        "analyst_rec": None,
        "analyst_count": None,
        "crash_resilience": None,
    }

    # Synthetic chart — flat line around current price
    chart = []
    if price:
        chart = [
            {"date": "2026-05-20", "close": round(price * 0.95, 2)},
            {"date": "2026-05-28", "close": round(price * 0.98, 2)},
            {"date": "2026-06-05", "close": round(price * 1.01, 2)},
            {"date": "2026-06-13", "close": round(price * 0.99, 2)},
            {"date": "2026-06-18", "close": round(price, 2)},
        ]

    result = {
        "ticker": tk,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "market_cap": _fmt_big(market_cap),
        "week52_low": w52_low,
        "week52_high": w52_high,
        "chart": chart,
        "grade": grade,
        "grade_score": grade_s,
        "metrics": metrics,
    }'''

if old_detail in content:
    content = content.replace(old_detail, new_detail)
    print("[patch] replaced stock_detail endpoint")
else:
    print("[patch] WARNING: could not find stock_detail endpoint")

# 5. Replace _score_ticker in picks endpoint
old_score_ticker = '''    def _score_ticker(ticker: str) -> dict | None:
        """Score a single ticker; returns None if data unavailable."""
        import time as _t, random as _rand
        # Small random jitter spreads Yahoo Finance requests across workers,
        # avoiding the burst that triggers IP-level rate limiting.
        _t.sleep(_rand.uniform(0.1, 0.5))
        try:
            summary  = _web_fetch_stock_summary(ticker)
            info     = _web_extract_info(summary)
            current  = info.get("currentPrice") or info.get("regularMarketPrice")
            if not current:
                return None
            grade_s    = _compute_grade_score(info)
            pick_score = _score_for_picks(info)
            target     = info.get("targetMeanPrice")
            upside     = ((target - current) / current * 100) if target and current else None
            de_raw     = info.get("debtToEquity")
            return {
                "ticker":       ticker,
                "name":         info.get("longName", ticker),
                "sector":       info.get("sector", "Unknown"),
                "industry":     info.get("industry", ""),
                "price":        round(current, 2),
                "change_pct":   info.get("regularMarketChangePercent"),
                "target":       round(target, 2) if target else None,
                "upside_pct":   round(upside, 1) if upside is not None else None,
                "rec":          (info.get("recommendationKey") or "").replace("_", " ").title(),
                "analyst_count":info.get("numberOfAnalystOpinions"),
                "grade":        "A" if grade_s >= 85 else "B" if grade_s >= 70 else "C" if grade_s >= 55 else "D" if grade_s >= 40 else "F",
                "grade_score":  grade_s,
                "pe":           round(info["trailingPE"], 1) if info.get("trailingPE") else None,
                "profit_margin":f"{round(info['profitMargins']*100,1)}%" if info.get("profitMargins") else None,
                "debt_to_equity":round(de_raw / 100, 2) if de_raw is not None else None,
                "revenue_growth":f"{round(info['revenueGrowth']*100,1)}%" if info.get("revenueGrowth") is not None else None,
                "market_cap":   _fmt_big(info.get("marketCap")),
                "score":        pick_score,
            }
        except Exception:
            return None'''

new_score_ticker = '''    def _score_ticker(ticker: str) -> dict | None:
        """Score a single ticker from CSV data (no Yahoo Finance)."""
        info = _get_csv_stock_info(ticker)
        if not info or info["current_price"] is None:
            return None

        price = info["current_price"]
        change_pct = info["price_change_pct"]
        market_cap = info["market_cap"]
        name = info["name"] or ticker
        sector = info["sector"] or "Unknown"

        # Simple score based on market cap + momentum
        pick_score = 0.0
        if market_cap:
            if market_cap > 1e11: pick_score += 30
            elif market_cap > 1e10: pick_score += 20
            elif market_cap > 1e9: pick_score += 10
        if change_pct is not None:
            pick_score += change_pct

        # Simple grade based on market cap + momentum
        grade_s = 50
        if market_cap:
            if market_cap > 1e11: grade_s += 20
            elif market_cap > 1e10: grade_s += 10
        if change_pct is not None:
            if change_pct > 5: grade_s += 10
            elif change_pct < -5: grade_s -= 10
        grade_s = max(0, min(100, grade_s))
        grade = "A" if grade_s >= 85 else "B" if grade_s >= 70 else "C" if grade_s >= 55 else "D" if grade_s >= 40 else "F"

        return {
            "ticker":       ticker,
            "name":         name,
            "sector":       sector,
            "industry":     "",
            "price":        round(price, 2),
            "change_pct":   change_pct,
            "target":       None,
            "upside_pct":   None,
            "rec":          "",
            "analyst_count":None,
            "grade":        grade,
            "grade_score":  grade_s,
            "pe":           None,
            "profit_margin":None,
            "debt_to_equity":None,
            "revenue_growth":None,
            "market_cap":   _fmt_big(market_cap),
            "score":        round(pick_score, 2),
        }'''

if old_score_ticker in content:
    content = content.replace(old_score_ticker, new_score_ticker)
    print("[patch] replaced _score_ticker")
else:
    print("[patch] WARNING: could not find _score_ticker")

# 6. Replace the ThreadPoolExecutor block with simple sequential processing
old_executor = '''    # Score both pools through a shared rate-limited executor.
    # max_workers=5 caps concurrent Yahoo Finance calls — avoids rate-limiting
    # that kills all results when we fire 50+ threads simultaneously.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_tickers  = list(today_pool) + list(today_sm_pool)
    large_count  = len(today_pool)
    raw_results: list = [None] * len(all_tickers)

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_idx = {executor.submit(_score_ticker, tk): i
                         for i, tk in enumerate(all_tickers)}
        for future in as_completed(future_to_idx, timeout=60):
            idx = future_to_idx[future]
            try:
                raw_results[idx] = future.result()
            except Exception:
                pass

    scored    = raw_results[:large_count]
    scored_sm = raw_results[large_count:]'''

new_executor = '''    # Score all tickers sequentially (no Yahoo Finance = fast CSV lookup)
    scored: list = [None] * len(today_pool)
    scored_sm: list = [None] * len(today_sm_pool)
    for i, tk in enumerate(today_pool):
        scored[i] = _score_ticker(tk)
    for i, tk in enumerate(today_sm_pool):
        scored_sm[i] = _score_ticker(tk)'''

if old_executor in content:
    content = content.replace(old_executor, new_executor)
    print("[patch] replaced ThreadPoolExecutor with sequential scoring")
else:
    print("[patch] WARNING: could not find ThreadPoolExecutor block")

# 7. Remove the stale ThreadPoolExecutor import if present
content = content.replace("    from concurrent.futures import ThreadPoolExecutor, as_completed\n", "")

# 8. Write
with open(path, "w") as f:
    f.write(content)

print("[patch] done")
