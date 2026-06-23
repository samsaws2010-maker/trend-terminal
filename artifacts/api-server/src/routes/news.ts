import { Router, type IRouter } from "express";

const PYTHON_BASE = `http://localhost:${process.env.PYTHON_SERVICE_PORT ?? 5100}`;

const router: IRouter = Router();

router.get("/market/news-sentiment", async (req, res): Promise<void> => {
  const tickers = req.query.tickers as string | undefined;
  const url = tickers
    ? `${PYTHON_BASE}/internal/market/news-sentiment?tickers=${encodeURIComponent(tickers)}`
    : `${PYTHON_BASE}/internal/market/news-sentiment`;
  try {
    const pyRes = await fetch(url, { signal: AbortSignal.timeout(30_000) });
    if (!pyRes.ok) {
      res.status(502).json({ error: "Market news sentiment error" });
      return;
    }
    const data = await pyRes.json();
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch market news sentiment");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/news/posts", async (req, res): Promise<void> => {
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/news/posts`);
    if (!pyRes.ok) {
      res.status(502).json({ error: "Failed to fetch news posts" });
      return;
    }
    const data = await pyRes.json();
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch news posts");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.post("/news/classify", async (req, res): Promise<void> => {
  const { headline } = req.body as { headline?: string };
  if (!headline || typeof headline !== "string") {
    res.status(400).json({ error: "headline is required" });
    return;
  }
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/news/classify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ headline }),
    });
    if (!pyRes.ok) {
      res.status(502).json({ error: "Classifier error" });
      return;
    }
    const data = await pyRes.json();
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to classify news headline");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/market/broad-sentiment", async (req, res): Promise<void> => {
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/market/broad-sentiment`, {
      signal: AbortSignal.timeout(35_000),
    });
    if (!pyRes.ok) { res.status(502).json({ error: "Broad sentiment error" }); return; }
    res.json(await pyRes.json());
  } catch (err) {
    req.log.error({ err }, "Failed to fetch broad market sentiment");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/stock/picks", async (req, res): Promise<void> => {
  try {
    const shuffle = req.query.shuffle ? `?shuffle=${req.query.shuffle}` : "";
    const pyRes = await fetch(`${PYTHON_BASE}/internal/stock/picks${shuffle}`, {
      signal: AbortSignal.timeout(200_000),
    });
    if (!pyRes.ok) { res.status(502).json({ error: "Stock picks error" }); return; }
    res.json(await pyRes.json());
  } catch (err) {
    req.log.error({ err }, "Failed to fetch stock picks");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/market/ticker-news/:ticker", async (req, res): Promise<void> => {
  const { ticker } = req.params;
  const tk = resolveTicker(ticker);
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/market/ticker-news/${encodeURIComponent(tk)}`, {
      signal: AbortSignal.timeout(20_000),
    });
    if (!pyRes.ok) { res.status(502).json({ error: "Ticker news error" }); return; }
    res.json(await pyRes.json());
  } catch (err) {
    req.log.error({ err }, "Failed to fetch ticker news sentiment");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

const TICKER_ALIASES: Record<string, string> = {
  APPL: "AAPL", FB: "META", BRKB: "BRK-B", "BRK.B": "BRK-B", GOOG: "GOOGL", BERK: "BRK-B", BERKSHIRE: "BRK-B",
};

function resolveTicker(t: string) {
  const normalized = t.toUpperCase().replace(".", "-");
  return TICKER_ALIASES[normalized] ?? normalized;
}

router.get("/market/gainers-losers", async (req, res): Promise<void> => {
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/market/gainers-losers`, {
      signal: AbortSignal.timeout(20_000),
    });
    if (!pyRes.ok) { res.status(502).json({ error: "Gainers/losers error" }); return; }
    res.json(await pyRes.json());
  } catch (err) {
    req.log.error({ err }, "Failed to fetch gainers/losers");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/stock/detail/:ticker", async (req, res): Promise<void> => {
  const { ticker } = req.params;
  const tk = resolveTicker(ticker);
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/stock/detail/${tk}`, {
      signal: AbortSignal.timeout(35_000),
    });
    const data = await pyRes.json();
    if (!pyRes.ok) {
      // Pass through 404 (not_found) vs other errors so the client can distinguish them
      const status = pyRes.status === 404 ? 404 : 502;
      res.status(status).json(data);
      return;
    }
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch stock detail");
    res.status(502).json({ error: "fetch_failed", message: "Python service unavailable" });
  }
});

/* ── Market Data (previous trading day OHLCV) ── */
router.get("/stock/market-data/:ticker", async (req, res): Promise<void> => {
  const { ticker } = req.params;
  const tk = resolveTicker(ticker);
  try {
    const pyRes = await fetch(`${PYTHON_BASE}/internal/stock/market-data/${tk}`, {
      signal: AbortSignal.timeout(20_000),
    });
    const data = await pyRes.json();
    if (!pyRes.ok) {
      res.status(pyRes.status).json(data);
      return;
    }
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch market data");
    res.status(502).json({ error: "fetch_failed", message: "Market data service unavailable" });
  }
});

export default router;
