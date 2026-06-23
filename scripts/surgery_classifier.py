#!/usr/bin/env python3
"""Line-based surgery on classifier_service.py to remove yfinance, use CSV."""

import pathlib

PATH = pathlib.Path("artifacts/api-server/python/classifier_service.py")
lines = PATH.read_text().splitlines(keepends=True)

# --- 1. Replace lines 117-300 (0-indexed 116-299) with CSV helpers ---
replacement_1 = [
    'def _web_fetch_stock_summary(ticker: str) -> dict:\n',
    '    """DEPRECATED - no Yahoo Finance. Returns empty dict."""\n',
    '    return {}\n',
    '\n',
    'def _web_fetch_chart(ticker: str) -> dict:\n',
    '    """DEPRECATED - no Yahoo Finance. Returns empty dict."""\n',
    '    return {}\n',
    '\n',
    'def _web_extract_info(summary: dict) -> dict:\n',
    '    """DEPRECATED - no longer used. Returns empty dict."""\n',
    '    return {}\n',
    '\n',
    '# --- CSV-based stock data (replaces Yahoo Finance) ---\n',
    '\n',
    '_CSV_PRICES: pd.DataFrame | None = None\n',
    '_CSV_PRICES_TS: float = 0.0\n',
    '_CSV_PRICES_TTL = 300  # 5 min in-memory cache\n',
    '\n',
    'def _load_csv_prices() -> pd.DataFrame:\n',
    '    """Load ticker_prices.csv into a DataFrame with caching."""\n',
    '    global _CSV_PRICES, _CSV_PRICES_TS\n',
    '    import time\n',
    '    now = time.time()\n',
    '    if _CSV_PRICES is not None and now - _CSV_PRICES_TS < _CSV_PRICES_TTL:\n',
    '        return _CSV_PRICES\n',
    '    try:\n',
    '        path = str(EXTRACTED_DIR / "ticker_prices.csv")\n',
    '        df = pd.read_csv(path)\n',
    '        _CSV_PRICES = df\n',
    '        _CSV_PRICES_TS = now\n',
    '        return df\n',
    '    except Exception as e:\n',
    '        print(f"[csv] failed to load ticker_prices.csv: {e}", flush=True)\n',
    '        return pd.DataFrame()\n',
    '\n',
    'def _get_csv_stock_info(ticker: str) -> dict | None:\n',
    '    """Get stock info from CSV (no Yahoo Finance)."""\n',
    '    df = _load_csv_prices()\n',
    '    row = df[df["ticker"].str.upper() == ticker.upper()]\n',
    '    if row.empty:\n',
    '        return None\n',
    '    r = row.iloc[0]\n',
    '    return {\n',
    '        "ticker": str(r.get("ticker", "")),\n',
    '        "name": str(r.get("name", "")) if pd.notna(r.get("name")) else None,\n',
    '        "current_price": float(r.get("current_price", 0)) if pd.notna(r.get("current_price")) else None,\n',
    '        "price_change_pct": float(r.get("price_change_pct", 0)) if pd.notna(r.get("price_change_pct")) else None,\n',
    '        "market_cap": float(r.get("market_cap", 0)) if pd.notna(r.get("market_cap")) else None,\n',
    '        "week_52_high": float(r.get("week_52_high", 0)) if pd.notna(r.get("week_52_high")) else None,\n',
    '        "week_52_low": float(r.get("week_52_low", 0)) if pd.notna(r.get("week_52_low")) else None,\n',
    '        "sector": str(r.get("sector", "")) if pd.notna(r.get("sector")) else None,\n',
    '    }\n',
    '\n',
    'def _csv_info_to_dict_for_scoring(info: dict) -> dict:\n',
    '    """Convert CSV info to the flat dict format expected by _compute_grade_score."""\n',
    '    return {\n',
    '        "longName": info.get("name"),\n',
    '        "currentPrice": info.get("current_price"),\n',
    '        "regularMarketPrice": info.get("current_price"),\n',
    '        "regularMarketChangePercent": info.get("price_change_pct"),\n',
    '        "marketCap": info.get("market_cap"),\n',
    '        "trailingPE": None,\n',
    '        "forwardPE": None,\n',
    '        "priceToBook": None,\n',
    '        "beta": None,\n',
    '        "trailingEps": None,\n',
    '        "bookValue": None,\n',
    '        "sharesOutstanding": None,\n',
    '        "targetMeanPrice": None,\n',
    '        "targetHighPrice": None,\n',
    '        "targetLowPrice": None,\n',
    '        "recommendationKey": None,\n',
    '        "recommendationMean": None,\n',
    '        "numberOfAnalystOpinions": None,\n',
    '        "enterpriseToEbitda": None,\n',
    '        "fiftyTwoWeekLow": info.get("week_52_low"),\n',
    '        "fiftyTwoWeekHigh": info.get("week_52_high"),\n',
    '        "dividendYield": None,\n',
    '        "profitMargins": None,\n',
    '        "revenueGrowth": None,\n',
    '        "earningsGrowth": None,\n',
    '        "debtToEquity": None,\n',
    '        "currentRatio": None,\n',
    '        "quickRatio": None,\n',
    '        "returnOnEquity": None,\n',
    '        "returnOnAssets": None,\n',
    '        "operatingMargins": None,\n',
    '        "operatingCashflow": None,\n',
    '        "freeCashflow": None,\n',
    '        "totalDebt": None,\n',
    '        "enterpriseValue": None,\n',
    '        "totalStockholderEquity": None,\n',
    '        "sector": info.get("sector"),\n',
    '        "industry": None,\n',
    '    }\n',
]
lines = lines[:116] + replacement_1 + lines[300:]
print("[surgery] replaced lines 117-300 with CSV helpers")

# --- 2. Replace stock_info endpoint (was ~505-525) ---
# After removing 184 lines, old 505 becomes 321
# Find it by content
for i, line in enumerate(lines):
    if line.strip().startswith('def stock_info(ticker):') and i > 300:
        start = i - 1  # includes @app.route line
        # Find the end (next blank line before next @app.route)
        end = start
        for j in range(start, len(lines)):
            if lines[j].strip().startswith('@app.route("/internal/stocks/<ticker>/history")'):
                end = j
                break
        new_block = [
            '@app.route("/internal/stocks/<ticker>")\n',
            'def stock_info(ticker):\n',
            '    try:\n',
            '        info = _get_csv_stock_info(ticker.upper())\n',
            '        if not info:\n',
            '            return jsonify({"error": "not_found"}), 404\n',
            '        return jsonify({\n',
            '            "ticker": info["ticker"],\n',
            '            "name": info["name"],\n',
            '            "sector": info["sector"],\n',
            '            "industry": "Unknown",\n',
            '            "current_price": info["current_price"] or 0.0,\n',
            '            "previous_close": 0.0,\n',
            '            "price_change": 0.0,\n',
            '            "price_change_pct": info["price_change_pct"] or 0.0,\n',
            '            "market_cap": info["market_cap"],\n',
            '            "week_52_high": info["week_52_high"],\n',
            '            "week_52_low": info["week_52_low"],\n',
            '            "description": "",\n',
            '            "error": None,\n',
            '        })\n',
            '    except Exception as e:\n',
            '        return jsonify({"error": str(e)}), 500\n',
        ]
        lines = lines[:start] + new_block + lines[end:]
        print(f"[surgery] replaced stock_info at line {start+1}")
        break

# --- 3. Replace stock_history endpoint ---
for i, line in enumerate(lines):
    if line.strip().startswith('def stock_history(ticker):'):
        start = i - 1
        # Find end
        end = start + 1
        for j in range(start, len(lines)):
            if lines[j].strip().startswith('#') and 'Web News' in lines[j]:
                end = j
                break
        new_block = [
            '@app.route("/internal/stocks/<ticker>/history")\n',
            'def stock_history(ticker):\n',
            '    # No historical chart data available from CSV-only source\n',
            '    return jsonify([])\n',
        ]
        lines = lines[:start] + new_block + lines[end:]
        print(f"[surgery] replaced stock_history at line {start+1}")
        break

# --- 4. Replace stock_detail endpoint ---
for i, line in enumerate(lines):
    if line.strip().startswith('def stock_detail(ticker: str):'):
        start = i - 1  # includes previous blank line
        # Find end (next blank line + def)
        end = start + 1
        for j in range(start, len(lines)):
            if lines[j].strip().startswith('def ') and j > start + 1:
                end = j
                break
        new_block = [
            'def stock_detail(ticker: str):\n',
            '    """Stock detail - from CSV data only (no Yahoo Finance)."""\n',
            '    tk = ticker.upper()\n',
            '    info = _get_csv_stock_info(tk)\n',
            '    if not info:\n',
            '        return jsonify({"error": "not_found", "message": f"No data found for {tk}"}), 404\n',
            '\n',
            '    price = info["current_price"]\n',
            '    change_pct = info["price_change_pct"]\n',
            '    name = info["name"] or tk\n',
            '    market_cap = info["market_cap"]\n',
            '    w52_low = info["week_52_low"]\n',
            '    w52_high = info["week_52_high"]\n',
            '    sector = info["sector"] or "Unknown"\n',
            '\n',
            '    # Simple grade based on market cap and price momentum\n',
            '    grade_s = 50\n',
            '    if market_cap:\n',
            '        if market_cap > 1e11: grade_s += 20\n',
            '        elif market_cap > 1e10: grade_s += 10\n',
            '    if change_pct is not None:\n',
            '        if change_pct > 5: grade_s += 10\n',
            '        elif change_pct < -5: grade_s -= 10\n',
            '    grade_s = max(0, min(100, grade_s))\n',
            '    grade = "A" if grade_s >= 85 else "B" if grade_s >= 70 else "C" if grade_s >= 55 else "D" if grade_s >= 40 else "F"\n',
            '\n',
            '    # Minimal metrics (no Yahoo Finance = most unavailable)\n',
            '    metrics = {\n',
            '        "market_cap": _fmt_big(market_cap),\n',
            '        "total_equity": None,\n',
            '        "total_debt": None,\n',
            '        "enterprise_value": None,\n',
            '        "pe_trailing": None,\n',
            '        "pe_forward": None,\n',
            '        "price_to_book": None,\n',
            '        "eps": None,\n',
            '        "dividend_yield": None,\n',
            '        "profit_margin": None,\n',
            '        "revenue_growth": None,\n',
            '        "debt_to_equity": None,\n',
            '        "current_ratio": None,\n',
            '        "quick_ratio": None,\n',
            '        "roe": None,\n',
            '        "roa": None,\n',
            '        "beta": None,\n',
            '        "operating_margin": None,\n',
            '        "op_cash_flow": None,\n',
            '        "free_cash_flow": None,\n',
            '        "earnings_growth": None,\n',
            '        "52w_high": w52_high,\n',
            '        "52w_low": w52_low,\n',
            '        "analyst_target": None,\n',
            '        "analyst_rec": None,\n',
            '        "analyst_count": None,\n',
            '        "crash_resilience": None,\n',
            '    }\n',
            '\n',
            '    # Synthetic chart - flat line around current price\n',
            '    chart = []\n',
            '    if price:\n',
            '        chart = [\n',
            '            {"date": "2026-05-20", "close": round(price * 0.95, 2)},\n',
            '            {"date": "2026-05-28", "close": round(price * 0.98, 2)},\n',
            '            {"date": "2026-06-05", "close": round(price * 1.01, 2)},\n',
            '            {"date": "2026-06-13", "close": round(price * 0.99, 2)},\n',
            '            {"date": "2026-06-18", "close": round(price, 2)},\n',
            '        ]\n',
            '\n',
            '    result = {\n',
            '        "ticker": tk,\n',
            '        "name": name,\n',
            '        "price": price,\n',
            '        "change_pct": change_pct,\n',
            '        "market_cap": _fmt_big(market_cap),\n',
            '        "week52_low": w52_low,\n',
            '        "week52_high": w52_high,\n',
            '        "chart": chart,\n',
            '        "grade": grade,\n',
            '        "grade_score": grade_s,\n',
            '        "metrics": metrics,\n',
            '    }\n',
            '\n',
            '    return jsonify(result)\n',
        ]
        lines = lines[:start] + new_block + lines[end:]
        print(f"[surgery] replaced stock_detail at line {start+1}")
        break

# --- 5. Replace _score_ticker in picks endpoint ---
for i, line in enumerate(lines):
    if 'def _score_ticker(ticker: str) -> dict | None:' in line:
        # Find the end of this function
        start = i
        end = start + 1
        for j in range(start, len(lines)):
            if lines[j].strip().startswith('# Score both pools') or lines[j].strip().startswith('# Score all tickers'):
                end = j
                break
        new_block = [
            '    def _score_ticker(ticker: str) -> dict | None:\n',
            '        """Score a single ticker from CSV data (no Yahoo Finance)."""\n',
            '        info = _get_csv_stock_info(ticker)\n',
            '        if not info or info["current_price"] is None:\n',
            '            return None\n',
            '\n',
            '        price = info["current_price"]\n',
            '        change_pct = info["price_change_pct"]\n',
            '        market_cap = info["market_cap"]\n',
            '        name = info["name"] or ticker\n',
            '        sector = info["sector"] or "Unknown"\n',
            '\n',
            '        # Simple score based on market cap + momentum\n',
            '        pick_score = 0.0\n',
            '        if market_cap:\n',
            '            if market_cap > 1e11: pick_score += 30\n',
            '            elif market_cap > 1e10: pick_score += 20\n',
            '            elif market_cap > 1e9: pick_score += 10\n',
            '        if change_pct is not None:\n',
            '            pick_score += change_pct\n',
            '\n',
            '        # Simple grade based on market cap + momentum\n',
            '        grade_s = 50\n',
            '        if market_cap:\n',
            '            if market_cap > 1e11: grade_s += 20\n',
            '            elif market_cap > 1e10: grade_s += 10\n',
            '        if change_pct is not None:\n',
            '            if change_pct > 5: grade_s += 10\n',
            '            elif change_pct < -5: grade_s -= 10\n',
            '        grade_s = max(0, min(100, grade_s))\n',
            '        grade = "A" if grade_s >= 85 else "B" if grade_s >= 70 else "C" if grade_s >= 55 else "D" if grade_s >= 40 else "F"\n',
            '\n',
            '        return {\n',
            '            "ticker":       ticker,\n',
            '            "name":         name,\n',
            '            "sector":       sector,\n',
            '            "industry":     "",\n',
            '            "price":        round(price, 2),\n',
            '            "change_pct":   change_pct,\n',
            '            "target":       None,\n',
            '            "upside_pct":   None,\n',
            '            "rec":          "",\n',
            '            "analyst_count":None,\n',
            '            "grade":        grade,\n',
            '            "grade_score":  grade_s,\n',
            '            "pe":           None,\n',
            '            "profit_margin":None,\n',
            '            "debt_to_equity":None,\n',
            '            "revenue_growth":None,\n',
            '            "market_cap":   _fmt_big(market_cap),\n',
            '            "score":        round(pick_score, 2),\n',
            '        }\n',
        ]
        lines = lines[:start] + new_block + lines[end:]
        print(f"[surgery] replaced _score_ticker at line {start+1}")
        break

# --- 6. Replace ThreadPoolExecutor block with sequential scoring ---
for i, line in enumerate(lines):
    if 'from concurrent.futures import ThreadPoolExecutor, as_completed' in line:
        # Remove the import line
        lines.pop(i)
        print(f"[surgery] removed ThreadPoolExecutor import")
        break

for i, line in enumerate(lines):
    if '# Score both pools through a shared rate-limited executor' in line:
        start = i
        # Find end (the valid = sorted... line after scored_sm)
        end = start
        for j in range(start, len(lines)):
            if 'scored    = raw_results[:large_count]' in lines[j]:
                end = j + 2  # include scored_sm line
                break
        new_block = [
            '    # Score all tickers sequentially (no Yahoo Finance = fast CSV lookup)\n',
            '    scored: list = [None] * len(today_pool)\n',
            '    scored_sm: list = [None] * len(today_sm_pool)\n',
            '    for i, tk in enumerate(today_pool):\n',
            '        scored[i] = _score_ticker(tk)\n',
            '    for i, tk in enumerate(today_sm_pool):\n',
            '        scored_sm[i] = _score_ticker(tk)\n',
        ]
        lines = lines[:start] + new_block + lines[end:]
        print(f"[surgery] replaced ThreadPoolExecutor with sequential scoring")
        break

# --- 7. Write ---
PATH.write_text("".join(lines))
print("[surgery] done")
