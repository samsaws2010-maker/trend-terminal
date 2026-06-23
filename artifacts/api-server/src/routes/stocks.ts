import { Router, type IRouter } from "express";

const PYTHON_BASE = `http://localhost:${process.env.PYTHON_SERVICE_PORT ?? 5100}`;

async function proxyGet(path: string, params?: Record<string, string | undefined>) {
  const url = new URL(`${PYTHON_BASE}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, v);
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`Python service error ${res.status}: ${path}`);
  return res.json();
}

const TICKER_ALIASES: Record<string, string> = {
  APPL: "AAPL", FB: "META", BRKB: "BRK-B", "BRK.B": "BRK-B", GOOG: "GOOGL", BERK: "BRK-B", BERKSHIRE: "BRK-B",
};

function resolveTicker(t: string) {
  const normalized = t.toUpperCase().replace(".", "-");
  return TICKER_ALIASES[normalized] ?? normalized;
}

const router: IRouter = Router();

router.get("/stocks/prices", async (req, res): Promise<void> => {
  try {
    const data = await proxyGet("/internal/stocks/prices");
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch ticker prices");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/stocks/:ticker", async (req, res): Promise<void> => {
  const raw = Array.isArray(req.params.ticker) ? req.params.ticker[0] : req.params.ticker;
  const ticker = resolveTicker(raw);
  try {
    const data = await proxyGet(`/internal/stocks/${ticker}`);
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch stock info");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/stocks/:ticker/history", async (req, res): Promise<void> => {
  const raw = Array.isArray(req.params.ticker) ? req.params.ticker[0] : req.params.ticker;
  const ticker = resolveTicker(raw);
  try {
    const data = await proxyGet(`/internal/stocks/${ticker}/history`, {
      period: req.query.period as string | undefined,
    });
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch stock history");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

router.get("/market/movers", async (req, res): Promise<void> => {
  try {
    const data = await proxyGet("/internal/market/movers");
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to fetch market movers");
    res.status(502).json({ error: "Python service unavailable" });
  }
});

export default router;
