import { Router, type IRouter } from "express";

const router: IRouter = Router();

const MOCK = {
  status: "ok",
  message: "Python service not deployed - mock mode enabled",
  data: []
};

router.get("/market/news-sentiment", async (_req, res) => {
  res.json(MOCK);
});

router.get("/news/posts", async (_req, res) => {
  res.json(MOCK);
});

router.post("/news/classify", async (_req, res) => {
  res.json({
    status: "ok",
    sentiment: "neutral",
    confidence: 0.5
  });
});

router.get("/market/broad-sentiment", async (_req, res) => {
  res.json(MOCK);
});

router.get("/stock/picks", async (_req, res) => {
  res.json(MOCK);
});

router.get("/market/ticker-news/:ticker", async (_req, res) => {
  res.json(MOCK);
});

router.get("/market/gainers-losers", async (_req, res) => {
  res.json(MOCK);
});

router.get("/stock/detail/:ticker", async (req, res) => {
  res.json({
    status: "ok",
    ticker: req.params.ticker,
    price: 0,
    change: 0
  });
});

router.get("/stock/market-data/:ticker", async (req, res) => {
  res.json({
    status: "ok",
    ticker: req.params.ticker,
    ohlcv: []
  });
});

export default router;