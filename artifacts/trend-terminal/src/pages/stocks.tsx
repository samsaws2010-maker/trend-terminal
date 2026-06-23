import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useGetTickerPrices } from "@workspace/api-client-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Zap, TrendingUp, BarChart2, ChevronDown, ChevronUp,
  ExternalLink, RefreshCw, ArrowLeft, Search, Star, X,
  Bookmark, BookmarkPlus, BookmarkMinus,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Label,
} from "recharts";

/* ─── types ──────────────────────────────────────────────────────────────────── */

interface WebArticle {
  title: string; provider: string; pub_date: string; url: string;
  label: "Positive" | "Negative" | "Neutral";
}
interface WebTickerSentiment {
  ticker: string; positive_pct: number; negative_pct: number;
  neutral_pct: number; dominant_sentiment: string;
  article_count: number; articles: WebArticle[];
}
interface BroadSentiment {
  score: number; total_articles: number;
  positive_count: number; negative_count: number; neutral_count: number;
  top_headlines: { title: string; source: string; label: string; provider: string; url: string; pub_date: string }[];
}
interface StockPick {
  ticker: string; name: string; sector: string; industry: string;
  price: number; change_pct: number | null; target: number | null;
  upside_pct: number | null; analyst_count: number | null;
  grade: string; grade_score: number; pe: number | null;
  forward_pe: number | null; dividend_yield: string | null;
  profit_margin: string | null; debt_to_equity: number | null;
  revenue_growth: string | null; market_cap: string | null; score: number;
  crash_resilience: string | null; beta: number | null;
  current_ratio: number | null;
}
interface StockMetrics {
  market_cap: string | null; sector: string | null; total_equity: string | null; total_debt: string | null;
  enterprise_value: string | null; pe_trailing: number | null; pe_forward: number | null;
  price_to_book: number | null; eps: string | null; dividend_yield: string | null;
  profit_margin: string | null; revenue_growth: string | null;
  debt_to_equity: number | null; current_ratio: number | null; quick_ratio: number | null;
  roe: string | null; roa: string | null; beta: number | null;
  operating_margin: string | null; op_cash_flow: string | null; free_cash_flow: string | null;
  earnings_growth: string | null; "52w_high": number | null; "52w_low": number | null;
  analyst_target: number | null; analyst_rec: string | null; analyst_count: number | null;
  crash_resilience: string | null;
}
interface MarketData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change_pct: number;
  prev_close: number;
  source: string;
  data_type: string;
  last_updated: string;
}
interface MarketMover {
  ticker: string;
  name: string;
  price: number;
  change_pct: number;
}
interface StockDetailData {
  ticker: string; name: string; price: number | null; change_pct: number | null;
  market_cap: string | null; week52_low: number | null; week52_high: number | null;
  chart: { date: string; close: number }[];
  grade: string; grade_score: number; metrics: StockMetrics;
}

/* ─── helpers ────────────────────────────────────────────────────────────────── */

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

function heatLabel(s: number) {
  if (s >= 80) return "Extremely Bullish";
  if (s >= 60) return "Bullish";
  if (s >= 40) return "Neutral";
  if (s >= 20) return "Bearish";
  return "Extremely Bearish";
}
function heatColor(s: number) {
  if (s >= 80) return "#006400";
  if (s >= 60) return "#7a9e2a";
  if (s >= 40) return "#d97706";
  if (s >= 20) return "#ea580c";
  return "#dc2626";
}
function gradeColor(g: string) {
  if (g === "A" || g === "A+") return "#006400";
  if (g === "B" || g === "B+") return "#7a9e2a";
  if (g === "C") return "#d97706";
  if (g === "D") return "#ea580c";
  return "#dc2626";
}
function gradeDesc(g: string) {
  if (g === "A") return "Excellent fundamentals";
  if (g === "B") return "Solid company with minor weaknesses";
  if (g === "C") return "Average — some concerns worth watching";
  if (g === "D") return "Weak fundamentals, elevated risk";
  return "Poor fundamentals — high-risk territory";
}
function metricQuality(key: string, val: unknown): "good" | "neutral" | "bad" | null {
  if (val === null || val === undefined) return null;
  const s = String(val);
  const n = typeof val === "number" ? val : parseFloat(s.replace(/[%$TBM]/g, ""));
  if (key === "pe_trailing" || key === "pe_forward") { return n > 0 && n <= 25 ? "good" : n <= 40 ? "neutral" : "bad"; }
  if (key === "debt_to_equity") { return n < 0.5 ? "good" : n < 1.5 ? "neutral" : "bad"; }
  if (key === "current_ratio" || key === "quick_ratio") { return n >= 1.5 ? "good" : n >= 1 ? "neutral" : "bad"; }
  if (key === "beta") { return n < 0.9 ? "good" : n < 1.3 ? "neutral" : "bad"; }
  if (key === "free_cash_flow" || key === "op_cash_flow") { return s.startsWith("-") ? "bad" : "good"; }
  if (["profit_margin","operating_margin","roe","roa","revenue_growth","earnings_growth"].includes(key)) {
    if (s.startsWith("-")) return "bad";
    return parseFloat(s) >= 10 ? "good" : "neutral";
  }
  if (key === "analyst_rec") {
    const n = s.toUpperCase().replace(/\s+/g, "_");
    return ["STRONG_BUY","BUY"].includes(n) ? "good" : n === "HOLD" ? "neutral" : "bad";
  }
  return null;
}
function qualityStyle(q: "good" | "neutral" | "bad" | null) {
  if (q === "good") return "text-[#7a9e2a]";
  if (q === "bad") return "text-[#dc2626]";
  if (q === "neutral") return "text-[#d97706]";
  return "text-foreground";
}
function labelBadge(label: string) {
  if (label === "Positive") return "bg-[#dcfce7] text-[#7a9e2a] border-[#7a9e2a]/50";
  if (label === "Negative") return "bg-[#fee2e2] text-[#dc2626] border-[#dc2626]/50";
  return "bg-[#f8faf5] text-[#d97706] border-[#d97706]/50";
}
function fmtDate(iso: string) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}); }
  catch { return iso.slice(0,10); }
}
const PROVIDER_COLORS: Record<string,string> = {
  "Web":"text-[#a78bfa]","Web Video":"text-[#a78bfa]",
  "Reuters":"text-[#3b82f6]","Bloomberg":"text-[#f59e0b]","CNBC":"text-[#dc2626]",
  "WSJ":"text-[#a78bfa]","Motley Fool":"text-[#7a9e2a]","Zacks":"text-[#06b6d4]",
  "TheStreet":"text-[#f97316]","MT Newswires":"text-[#64748b]",
};

// Flat fundamentals grid — show only data we actually have from CSV
const FUND_GRID: { label: string; key: keyof StockMetrics; prefix?: string }[] = [
  {label:"MARKET CAP",  key:"market_cap"},
  {label:"SECTOR",      key:"sector"},
  {label:"52W HIGH",    key:"52w_high"},
  {label:"52W LOW",     key:"52w_low"},
  {label:"P/E",         key:"pe_trailing"},
  {label:"FWD P/E",     key:"pe_forward"},
  {label:"P/B",         key:"price_to_book"},
  {label:"EPS",         key:"eps"},
  {label:"DIV YIELD",   key:"dividend_yield"},
  {label:"PROFIT MARGIN",key:"profit_margin"},
  {label:"REV GROWTH",  key:"revenue_growth"},
  {label:"D/E",         key:"debt_to_equity"},
  {label:"CURRENT RATIO",key:"current_ratio"},
  {label:"QUICK RATIO", key:"quick_ratio"},
  {label:"ROE",         key:"roe"},
  {label:"ROA",         key:"roa"},
];

/* ─── StockDetail ────────────────────────────────────────────────────────────── */

function StockDetail({ticker, sentiment: sentimentProp, broad, onBack}: {
  ticker: string; sentiment?: WebTickerSentiment; broad?: BroadSentiment | null; onBack: () => void;
}) {
  const [detail, setDetail] = useState<StockDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ type: string; message?: string } | null>(null);
  const [fetchedSentiment, setFetchedSentiment] = useState<WebTickerSentiment | null>(null);
  const [sentimentFetching, setSentimentFetching] = useState(!sentimentProp);
  const [marketData, setMarketData] = useState<MarketData | null>(null);
  const [marketDataLoading, setMarketDataLoading] = useState(false);
  const [chartData, setChartData] = useState<{ date: string; close: number; open: number; high: number; low: number; volume: number | null }[] | null>(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartRange, setChartRange] = useState<"1y" | "all">("1y");

  const sentiment = sentimentProp ?? fetchedSentiment ?? undefined;

  useEffect(() => {
    setDetail(null); setLoading(true); setError(null);
    setFetchedSentiment(null);
    setMarketData(null); setMarketDataLoading(false);
    setChartData(null); setChartLoading(false);
    fetch(`${BASE}/api/stock/detail/${ticker.toUpperCase()}`)
      .then(async r => {
        const d = await r.json();
        if (!r.ok || d.error) {
          setError({ type: d.error ?? "fetch_failed", message: d.message });
        } else {
          setDetail(d);
        }
      })
      .catch(() => setError({ type: "fetch_failed" }))
      .finally(() => setLoading(false));
  }, [ticker]);

  /* fetch market data when ticker changes */
  useEffect(() => {
    setMarketDataLoading(true);
    fetch(`${BASE}/api/stock/market-data/${ticker.toUpperCase()}?_=${Date.now()}`)
      .then(async r => {
        const d = await r.json();
        if (r.ok && !d.error) setMarketData(d);
        else setMarketData(null);
      })
      .catch(() => setMarketData(null))
      .finally(() => setMarketDataLoading(false));
  }, [ticker]);

  /* fetch chart data */
  useEffect(() => {
    setChartLoading(true);
    const period = chartRange === "all" ? "all" : "1y";
    fetch(`${BASE}/api/stocks/${ticker.toUpperCase()}/history?period=${period}&_=${Date.now()}`)
      .then(async r => {
        const d = await r.json();
        if (Array.isArray(d) && d.length > 0) {
          setChartData(d);
        } else {
          setChartData(null);
        }
      })
      .catch(() => setChartData(null))
      .finally(() => setChartLoading(false));
  }, [ticker, chartRange]);

  useEffect(() => {
    if (sentimentProp) { setSentimentFetching(false); return; }
    setSentimentFetching(true);
    fetch(`${BASE}/api/market/ticker-news/${ticker.toUpperCase()}`)
      .then(r => r.json())
      .then(d => { if (!d.error) setFetchedSentiment(d); })
      .catch(() => {})
      .finally(() => setSentimentFetching(false));
  }, [ticker, sentimentProp]);

  const priceUp = (detail?.change_pct ?? 0) >= 0;
  const noNews = !sentiment || sentiment.article_count === 0;

  // Raw article counts for accurate bar proportions
  const rawCounts = noNews ? { pos: 0, neu: 0, neg: 0 } : {
    pos: (sentiment?.articles ?? []).filter(a => a.label === "Positive").length,
    neu: (sentiment?.articles ?? []).filter(a => a.label === "Neutral").length,
    neg: (sentiment?.articles ?? []).filter(a => a.label === "Negative").length,
  };
  const rawTotal = rawCounts.pos + rawCounts.neu + rawCounts.neg;
  const rawPosPct = rawTotal > 0 ? Math.round(rawCounts.pos / rawTotal * 100) : 0;
  const rawNeuPct = rawTotal > 0 ? Math.round(rawCounts.neu / rawTotal * 100) : 0;
  const rawNegPct = rawTotal > 0 ? Math.round(rawCounts.neg / rawTotal * 100) : 0;

  const sentScore = noNews ? 50 : Math.round(sentiment?.positive_pct ?? 50);
  const sentSignal = noNews ? "Neutral" : heatLabel(sentScore);
  const crashColor = (r: string | null) => {
    if (r === "Strong") return "#7a9e2a";
    if (r === "Moderate") return "#d97706";
    if (r === "Below Average") return "#dc2626";
    return "#dc2626";
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-background">
      {/* ── header bar ── */}
      <div className="px-5 py-2.5 border-b border-border flex items-center gap-3 sticky top-0 z-10 bg-white/80 backdrop-blur-sm">
        <span className="font-bold text-base text-primary tracking-widest">
          ${ticker.toUpperCase()}
        </span>
        <button onClick={onBack}
          className="ml-auto flex items-center gap-1.5 text-[15px] tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors px-3 py-1 border border-border hover:border-primary/50 rounded-lg">
          <ArrowLeft className="w-3 h-3"/> Clear
        </button>
      </div>

      {loading && (
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-40 bg-muted"/>
            <Skeleton className="h-40 bg-muted"/>
          </div>
          <div className="grid grid-cols-4 gap-px">
            {Array.from({length:16}).map((_,i)=><Skeleton key={i} className="h-14 bg-muted"/>)}
          </div>
          <Skeleton className="h-32 bg-muted"/>
        </div>
      )}
      {error && (
        <div className="flex flex-col items-center justify-center gap-4 p-12 text-center">
          {error.type === "not_found" ? (
            <>
              <div className="text-3xl">🔍</div>
              <div className="font-sans font-bold text-base text-foreground">Ticker not found</div>
              <div className="text-sm text-muted-foreground max-w-xs">
                <span className="font-sans text-primary">{ticker.toUpperCase()}</span> didn't return any data.
                Double-check the symbol and try again.
              </div>
            </>
          ) : (
            <>
              <div className="text-3xl">⚠️</div>
              <div className="font-sans font-bold text-base text-foreground">Couldn't load {ticker.toUpperCase()}</div>
              <div className="text-sm text-muted-foreground max-w-xs">
                Web data returned an error for this ticker. It may be temporarily unavailable — try again in a moment.
              </div>
            </>
          )}
          <button onClick={onBack} className="mt-2 text-sm font-mono px-3 py-1.5 rounded border border-border hover:border-primary/50 text-muted-foreground hover:text-foreground transition-colors">
            ← Back to Research
          </button>
        </div>
      )}

      {!loading && !error && detail && (
        <div className="flex flex-col">
          {/* ── news + price header ── */}
          <div className="grid grid-cols-[320px_1fr] border-b border-[hsl(var(--border))]">
            {/* News / Research panel */}
            <div className="border-r border-[hsl(var(--border))] p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-[15px] font-bold tracking-widest uppercase text-[hsl(var(--muted-foreground))]">≡ Research</span>
                <span className="text-[14px] font-bold tracking-widest px-2 py-0.5 border border-[#7C5CFC]/40 text-[#4a3b8c] font-mono bg-[#ede8ff]/50">
                  INSTITUTIONAL
                </span>
              </div>
              <div className="text-[15px] text-[hsl(var(--muted-foreground))] tracking-wide">
                News · Analyst Reports · Financial Headlines
              </div>
              <div className="h-px bg-[hsl(var(--border))]"/>

              {/* Sentiment bar — green/red only, no yellow */}
              {sentimentFetching ? (
                <div className="h-6 rounded-lg bg-[hsl(var(--border))] animate-pulse flex items-center px-2">
                  <span className="text-[14px] text-[hsl(var(--muted-foreground))] font-mono">LOADING…</span>
                </div>
              ) : !noNews ? (
                <div className="h-6 flex gap-px overflow-hidden rounded-lg">
                  <div className="bg-[#7a9e2a]/70" style={{width:`${rawPosPct}%`}}/>
                  <div className="bg-[#d97706]/70" style={{width:`${rawNeuPct}%`}}/>
                  <div className="bg-[#dc2626]/70" style={{width:`${rawNegPct}%`}}/>
                </div>
              ) : (
                <div className="h-6 flex gap-px overflow-hidden rounded-lg">
                  <div className="bg-[hsl(var(--muted-foreground))/40] w-1/2"/>
                  <div className="bg-[hsl(var(--border))] w-1/2 flex items-center justify-end pr-2">
                    <span className="text-[14px] text-[hsl(var(--muted-foreground))] font-mono">NO ARTICLES</span>
                  </div>
                </div>
              )}

              {/* Signal / articles */}
              <div className="space-y-1.5 font-mono">
                {[
                  {label:"ARTICLES ANALYZED", val: sentimentFetching ? "…" : String(sentiment?.article_count ?? 0), color:"hsl(var(--muted-foreground))"},
                  {label:"SIGNAL", val: sentimentFetching ? "…" : sentSignal,
                    color: sentimentFetching ? "hsl(var(--muted-foreground))" : heatColor(sentScore)},
                ].map(({label,val,color})=>(
                  <div key={label} className="flex items-baseline justify-between gap-2">
                    <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">{label}</span>
                    <span className="text-[15px] font-bold" style={{color}}>{val}</span>
                  </div>
                ))}
              </div>

              {/* Articles or empty state */}
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {sentimentFetching ? (
                  <div className="space-y-1.5">
                    {[0,1,2].map(i => (
                      <div key={i} className="h-8 rounded bg-[hsl(var(--muted))] animate-pulse"/>
                    ))}
                  </div>
                ) : (sentiment?.articles?.length ?? 0) > 0 ? (
                  (sentiment?.articles ?? []).map((a,i) => (
                    <div key={i} className="flex items-start gap-1.5 group">
                      <span className={`shrink-0 text-[15px] font-bold px-2 py-0.5 rounded border min-w-[2.5rem] text-center inline-flex justify-center items-center ${labelBadge(a.label)}`}>
                        {a.label==="Positive"?"P+":a.label==="Negative"?"N-":"="}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[15px] text-[hsl(var(--muted-foreground))] leading-snug group-hover:text-[hsl(var(--muted-foreground))]">{a.title}</p>
                        <span className={`text-[14px] ${PROVIDER_COLORS[a.provider]??"text-[hsl(var(--muted-foreground))]"}`}>{a.provider}</span>
                      </div>
                      {a.url && (
                        <a href={a.url} target="_blank" rel="noopener noreferrer"
                          className="shrink-0 text-[hsl(var(--muted-foreground))] hover:text-[#7a9e2a] mt-0.5">
                          <ExternalLink className="w-2.5 h-2.5"/>
                        </a>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-[15px] text-[hsl(var(--muted-foreground))] font-mono">
                    No news found for ${ticker.toUpperCase()}.
                  </p>
                )}
              </div>
            </div>

            {/* Price + meta */}
            <div className="p-5 flex flex-col justify-between">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))] mb-0.5">
                    $ {detail.name?.toUpperCase()} · LIVE PRICE
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono font-bold text-3xl text-[hsl(var(--foreground))]">
                      ${detail.price?.toFixed(2)}
                    </span>
                    <span className={`font-sans text-base font-bold ${priceUp?"text-[#006400]":"text-[#dc2626]"}`}>
                      {priceUp?"+":""}{((detail.change_pct ?? 0) * 100).toFixed(2)}%
                    </span>
                  </div>
                </div>
                {/* Grade badge */}
                <div className="text-right">
                  <div className="inline-flex items-baseline gap-1">
                    <span className="font-bold text-2xl font-mono" style={{color:gradeColor(detail.grade)}}>
                      {detail.grade}
                    </span>
                  </div>
                  <div className="text-[15px] text-[hsl(var(--muted-foreground))] mt-0.5">
                    MCap <span className="text-[hsl(var(--muted-foreground))]">{detail.market_cap}</span>
                  </div>
                  {detail.week52_low && detail.week52_high && (
                    <div className="text-[15px] text-[hsl(var(--muted-foreground))]">
                      52w{" "}
                      <span className="text-[hsl(var(--muted-foreground))] font-mono">${detail.week52_low} – ${detail.week52_high}</span>
                    </div>
                  )}
                  {/* Analyst target */}
                  {detail.metrics.analyst_target && detail.price && detail.price > 0 && (() => {
                    const t = Number(String(detail.metrics.analyst_target).replace(/,/g, ""));
                    const p = Number(detail.price);
                    const upside = (t - p) / p * 100;
                    return !isNaN(upside) && isFinite(upside) && (
                      <div className="text-[15px] text-[hsl(var(--muted-foreground))] mt-1">
                        Target{" "}
                        <span className="font-sans text-[#006400] font-bold">
                          ${detail.metrics.analyst_target}
                        </span>
                        <span className="ml-1 text-[#006400]">
                          ({upside.toFixed(1)}% up)
                        </span>
                      </div>
                    );
                  })()}
                  {detail.metrics.analyst_rec && detail.metrics.analyst_rec !== "N/A" && (() => {
                    const rec = detail.metrics.analyst_rec;
                    const recNorm = rec.toUpperCase().replace(/\s+/g, "_");
                    const recColor =
                      recNorm === "STRONG_BUY" ? "#006400" :
                      recNorm === "BUY"        ? "#006400" :
                      recNorm === "HOLD"       ? "#d97706" :
                      recNorm === "UNDERWEIGHT"? "#dc2626" :
                      recNorm === "SELL"       ? "#dc2626" :
                      recNorm === "STRONG_SELL"? "#dc2626" :
                      "#dc2626";
                    return (
                      <div className="text-[15px] text-[hsl(var(--muted-foreground))]">
                        {detail.metrics.analyst_count} Analysts ·{" "}
                        <span className="font-bold font-mono" style={{color: recColor}}>
                          {rec.replace("_"," ")}
                        </span>
                      </div>
                    );
                  })()}
                </div>
              </div>

              {/* ── Composite Signal ── */}
              <div className="mt-4 border border-[hsl(var(--border))] rounded-lg overflow-hidden bg-[hsl(var(--card))]">
                <div className="px-3 py-1.5 border-b border-[hsl(var(--border))]">
                  <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Composite Signal</span>
                </div>
                <div className="divide-y divide-[hsl(var(--border))]">
                  {/* Stock news sentiment */}
                  {(() => {
                    const sc = sentScore;
                    const sGrade = sc >= 80 ? "A" : sc >= 65 ? "B" : sc >= 50 ? "C" : sc >= 35 ? "D" : "F";
                    const sCol   = sc >= 80 ? "#006400" : sc >= 65 ? "#7a9e2a" : sc >= 50 ? "#d97706" : sc >= 35 ? "#ea580c" : "#dc2626";
                    return (
                      <div className="px-3 py-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Stock Sentiment</span>
                          <span className="text-[14px] font-mono font-bold" style={{color:sCol}}>{sGrade} ({sc}/100)</span>
                        </div>
                        <div className="h-1 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{width:`${sc}%`,backgroundColor:sCol}}/>
                        </div>
                      </div>
                    );
                  })()}
                  {/* Fundamentals grade */}
                  {(() => {
                    const fs = detail.grade_score;
                    return (
                      <div className="px-3 py-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Fundamentals</span>
                          <span className="text-[14px] font-mono font-bold" style={{color:gradeColor(detail.grade)}}>{detail.grade} ({fs}/100)</span>
                        </div>
                        <div className="h-1 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{width:`${fs}%`,backgroundColor:gradeColor(detail.grade)}}/>
                        </div>
                      </div>
                    );
                  })()}
                  {/* Composite — sentiment + fundamentals only, no market average */}
                  {(() => {
                    const composite = Math.round(sentScore * 0.2 + detail.grade_score * 0.8);
                    const cGrade = composite >= 88 ? "A+" : composite >= 80 ? "A" : composite >= 70 ? "B+" : composite >= 62 ? "B" : composite >= 52 ? "C" : "D";
                    const cCol   = composite >= 80 ? "#006400" : composite >= 62 ? "#7a9e2a" : composite >= 52 ? "#d97706" : "#dc2626";
                    return (
                      <div className="px-3 py-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Composite</span>
                          <span className="text-[14px] font-mono font-bold" style={{color:cCol}}>{cGrade} ({composite}/100)</span>
                        </div>
                        <div className="h-1.5 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{width:`${composite}%`,backgroundColor:cCol,boxShadow:`0 0 6px ${cCol}60`}}/>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>

          {/* ── Fundamentals flat grid ── */}
          <div className="border-b border-[hsl(var(--border))]">
            <div className="px-5 pt-3 pb-1">
              <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Fundamentals</span>
            </div>
            <div className="grid grid-cols-4 border-t border-l border-[hsl(var(--border))]">
              {FUND_GRID.map(({label, key}) => {
                const val = detail.metrics[key];
                // For P/E, fallback to forward P/E if trailing is missing
                const fallbackKey = key === "pe_trailing" ? "pe_forward" : undefined;
                const fallbackVal = fallbackKey ? detail.metrics[fallbackKey] : undefined;
                const displayVal = (val !== null && val !== undefined) ? val : fallbackVal;
                const hasVal = displayVal !== null && displayVal !== undefined;
                const displayLabel = key === "pe_trailing" && !val && fallbackVal ? "FWD P/E" : label;
                return (
                  <div key={key as string}
                    className="border-b border-r border-[hsl(var(--border))] px-4 py-3 space-y-1">
                    <div className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">{displayLabel}</div>
                    <div className={`font-sans text-sm font-bold ${hasVal ? "text-[hsl(var(--foreground))]" : "text-[hsl(var(--muted-foreground))]/40"}`}>
                      {hasVal ? String(displayVal) : "N/A"}
                    </div>
                  </div>
                );
              })}
              {/* Crash Resilience — full-width row */}
              <div className="col-span-4 border-b border-r border-[hsl(var(--border))] px-4 py-3 flex items-center gap-4">
                <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))] shrink-0">Crash Resilience</span>
                <span className="font-sans text-sm font-bold"
                  style={{color: detail.metrics.crash_resilience ? crashColor(detail.metrics.crash_resilience) : "hsl(var(--muted-foreground))40"}}>
                  {detail.metrics.crash_resilience ?? "N/A"}
                </span>
                <span className="text-[15px] text-[hsl(var(--muted-foreground))]">
                  · Beta {detail.metrics.beta ?? "N/A"} · D/E {detail.metrics.debt_to_equity ?? "N/A"} · Cur. Ratio {detail.metrics.current_ratio ?? "N/A"}
                </span>
              </div>
              {/* Market Data — 1-year chart + OHLCV */}
              <div className="col-span-4 border-b border-r border-[hsl(var(--border))] px-4 py-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Market Data</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setChartRange("1y")} className={`text-[9px] px-2 py-0.5 rounded font-mono transition-colors ${chartRange === "1y" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground"}`}>1Y</button>
                    <button onClick={() => setChartRange("all")} className={`text-[9px] px-2 py-0.5 rounded font-mono transition-colors ${chartRange === "all" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground"}`}>ALL</button>
                  </div>
                </div>
                {/* 1-year chart */}
                {chartLoading ? (
                  <Skeleton className="h-40 rounded w-full" />
                ) : chartData && chartData.length > 0 ? (
                  <div className="h-40 w-full flex flex-col">
                    <div className="h-32">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData} margin={{top:2,right:56,left:8,bottom:2}}>
                          <defs>
                            <linearGradient id={`priceGrad-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={chartData[chartData.length-1]?.close >= chartData[0]?.close ? "#006400" : "#dc2626"} stopOpacity={0.12}/>
                              <stop offset="100%" stopColor={chartData[chartData.length-1]?.close >= chartData[0]?.close ? "#006400" : "#dc2626"} stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <Tooltip
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const p = payload[0].payload as {date: string; close: number; high: number; low: number; volume: number | null};
                                return (
                                  <div className="bg-background border border-border rounded px-2 py-1 shadow-sm text-[11px] font-mono">
                                    <div className="text-muted-foreground">{p.date}</div>
                                    <div className="font-bold">${p.close.toFixed(2)}</div>
                                    <div className="text-muted-foreground">H: ${p.high?.toFixed(2)} L: ${p.low?.toFixed(2)}</div>
                                    {p.volume ? <div className="text-muted-foreground">Vol: {(p.volume/1e6).toFixed(1)}M</div> : null}
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <XAxis
                            dataKey="date"
                            axisLine={false}
                            tickLine={false}
                            tick={false}
                          />
                          <YAxis
                            domain={["auto", "auto"]}
                            orientation="right"
                            tick={{fontSize: 10, fontFamily: "monospace", fill: "hsl(var(--muted-foreground))"}}
                            axisLine={false}
                            tickLine={false}
                            width={50}
                            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                          />
                          <Area type="monotone" dataKey="close" stroke={chartData[chartData.length-1]?.close >= chartData[0]?.close ? "#006400" : "#dc2626"} strokeWidth={2} fill={`url(#priceGrad-${ticker})`} dot={false} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="relative text-[9px] font-mono text-[#9ca3af] leading-none h-4 pl-2 pr-14 pt-1">
                      {(() => {
                        const n = chartData.length;
                        // Find actual month boundaries
                        const monthIndices: number[] = [];
                        let lastMonth = -1;
                        chartData.forEach((pt, i) => {
                          const d = new Date(pt.date);
                          const m = d.getMonth();
                          if (m !== lastMonth) {
                            monthIndices.push(i);
                            lastMonth = m;
                          }
                        });
                        // Pick ~5 evenly spaced month labels
                        const pickCount = 5;
                        let indices: number[];
                        if (monthIndices.length <= pickCount) {
                          indices = monthIndices;
                        } else {
                          const step = (monthIndices.length - 1) / (pickCount - 1);
                          indices = Array.from({length: pickCount}, (_, i) => monthIndices[Math.round(i * step)]);
                        }
                        // Always ensure start and end are included
                        if (indices[0] !== 0) indices[0] = 0;
                        if (indices[indices.length - 1] !== n - 1) indices[indices.length - 1] = n - 1;
                        return indices.map((idx, i) => {
                          const date = new Date(chartData[idx].date);
                          const m = date.toLocaleString("en-US", {month: "short"});
                          const y = date.getFullYear();
                          const isFirst = i === 0;
                          const isLast = i === indices.length - 1;
                          const pct = (i / (indices.length - 1)) * 0.95;
                          return (
                            <span key={i} className="absolute top-0 whitespace-nowrap"
                              style={{
                                left: `${pct * 100}%`,
                                transform: isFirst ? 'none' : isLast ? 'translateX(-100%)' : 'translateX(-50%)'
                              }}>
                              {`${m} '${y.toString().slice(2)}`}
                            </span>
                          );
                        });
                      })()}
                    </div>
                  </div>
                ) : (
                  <div className="text-[15px] text-muted-foreground h-40 flex items-center">No chart data available.</div>
                )}
              </div>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

/* ─── MacroHeadlines ─────────────────────────────────────────────────────────── */

function MacroHeadlines({headlines}: {
  headlines: BroadSentiment["top_headlines"];
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? headlines : headlines.slice(0, 8);
  return (
    <div className="pt-2 border-t border-border/50 space-y-1.5">
      <div className="text-[14px] font-bold uppercase tracking-wider text-muted-foreground">
        Macro Headlines
      </div>
      {visible.map((h,i)=>(
        <div key={i} className="flex items-start gap-1.5 group">
          <span className={`shrink-0 text-[15px] font-bold px-2 py-0.5 rounded border min-w-[2.5rem] text-center inline-flex justify-center items-center ${labelBadge(h.label as "Positive"|"Negative"|"Neutral")}`}>
            {h.label==="Positive"?"P+":h.label==="Negative"?"N-":"="}
          </span>
          <div className="flex-1 min-w-0">
            {h.url ? (
              <a href={h.url} target="_blank" rel="noopener noreferrer"
                className="text-[15px] text-foreground/80 leading-tight hover:text-foreground group-hover:underline block">
                {h.title}
              </a>
            ) : (
              <span className="text-[15px] text-foreground/80 leading-tight">{h.title}</span>
            )}
            {h.provider && (
              <span className="text-[14px] text-muted-foreground/90">{h.provider}</span>
            )}
          </div>
        </div>
      ))}
      {headlines.length > 8 && (
        <button onClick={()=>setShowAll(s=>!s)}
          className="w-full text-center text-[14px] font-mono text-muted-foreground hover:text-foreground border border-border/50 hover:border-border rounded py-1 transition-colors mt-1">
          {showAll ? "▲ Collapse" : `▼ Show all ${headlines.length} articles`}
        </button>
      )}
    </div>
  );
}

/* ─── TopMovers ─────────────────────────────────────────────────────────────── */

function TopMovers({stocks, onClick, loading}: {stocks: MarketMover[]; onClick: (t: string) => void; loading: boolean}) {
  return (
    <div className="mt-4 border border-[hsl(var(--border))] rounded-lg overflow-hidden bg-[hsl(var(--card))]">
      <div className="px-3 py-1.5 border-b border-[hsl(var(--border))]">
        <span className="text-[14px] tracking-widest uppercase text-[hsl(var(--muted-foreground))]">Top 10 Market Cap</span>
      </div>
      <div className="divide-y divide-[hsl(var(--border))]">
        {loading ? (
          <div className="p-3 space-y-2">
            {[0,1,2,3,4,5,6,7,8,9].map(i => <Skeleton key={i} className="h-6 rounded"/>)}
          </div>
        ) : (
          <div className="px-3 py-2 space-y-1">
            {stocks.map(m => {
              const isUp = m.change_pct >= 0;
              const color = isUp ? "#006400" : "#dc2626";
              return (
                <div key={m.ticker} onClick={() => onClick(m.ticker)}
                  className="flex items-center justify-between cursor-pointer hover:bg-muted/30 rounded px-1 py-0.5 transition-colors">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-sans font-bold text-[15px] text-foreground shrink-0">${m.ticker}</span>
                    <span className="text-[12px] text-muted-foreground truncate">{m.name}</span>
                  </div>
                  <div className="text-right shrink-0 flex items-center gap-2">
                    <span className="text-[13px] font-mono text-foreground">${m.price.toFixed(2)}</span>
                    <span className="text-[13px] font-mono font-bold shrink-0" style={{color}}>
                      {isUp ? "+" : ""}{m.change_pct}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── PickCard ───────────────────────────────────────────────────────────────── */

function PickCard({pick, rank, compositeScore, onClick, watchlist, onToggleWatchlist}: {pick: StockPick; rank: number; compositeScore: number; onClick: () => void; watchlist?: string[]; onToggleWatchlist?: (ticker: string) => void}) {
  const c = heatColor(compositeScore);
  const grade = compositeScore >= 88 ? "A+" : compositeScore >= 80 ? "A" : compositeScore >= 70 ? "B+" : compositeScore >= 62 ? "B" : compositeScore >= 52 ? "C" : "D";
  const chgColor = (pick.change_pct ?? 0) >= 0 ? "#006400" : "#dc2626";
  const upside = pick.upside_pct ?? 0;
  const upsideColor = upside >= 20 ? "#006400" : upside >= 5 ? "#006400" : upside >= 0 ? "#d97706" : "#dc2626";
  const upsideBar = Math.min(100, Math.max(0, upside / 60 * 100));

  const margin = parseFloat((pick.profit_margin ?? "0").replace("%",""));
  const revGrw = parseFloat((pick.revenue_growth ?? "0").replace("%",""));
  const peVal = pick.pe ?? 0;

  const isTop = rank <= 3;

  const isWatched = watchlist?.includes(pick.ticker) ?? false;

  return (
    <div onClick={onClick}
      className="relative rounded-2xl cursor-pointer transition-all duration-200 hover:translate-y-[-2px] overflow-hidden group"
      style={{background:"white", border:`1px solid ${c}28`, boxShadow:`0 2px 12px ${c}08`}}>
      {/* left accent bar */}
      <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{background:`linear-gradient(to bottom,${c},${c}40)`}}/>

      <div className="p-3 pl-4">
        {/* row 1: rank + ticker + grade + price */}
        <div className="flex items-start justify-between gap-1 mb-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-[14px] text-muted-foreground font-mono shrink-0 w-6">#{rank}</span>
            <span className="font-sans font-bold text-[17px] text-foreground">${pick.ticker}</span>
            <div className="flex items-baseline gap-0.5 px-1.5 py-0.5 rounded border font-mono shrink-0"
              style={{color:c, borderColor:`${c}45`, background:`${c}12`}}>
              <span className="text-[14px] font-black">{grade}</span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="font-sans text-[15px] font-bold text-foreground">${pick.price?.toFixed(2)}</div>
            <div className="font-sans text-[14px]" style={{color:chgColor}}>
              {(pick.change_pct??0)>=0?"+":""}{((pick.change_pct ?? 0) * 100).toFixed(2)}%
            </div>
            {onToggleWatchlist && (
              <button
                onClick={e => { e.stopPropagation(); onToggleWatchlist(pick.ticker); }}
                className="mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                title={isWatched ? "Remove from watchlist" : "Add to watchlist"}
              >
                {isWatched ? (
                  <BookmarkMinus className="w-3.5 h-3.5 text-primary"/>
                ) : (
                  <BookmarkPlus className="w-3.5 h-3.5 text-muted-foreground hover:text-primary"/>
                )}
              </button>
            )}
          </div>
        </div>

        {/* company name */}
        <div className="text-[15px] text-muted-foreground/90 truncate mb-2">{pick.name}</div>

        {/* sector */}
        <div className="flex items-center gap-1.5 mb-2.5 flex-wrap">
          <span className="text-[14px] px-1.5 py-0.5 rounded border border-border/40 text-muted-foreground">{pick.sector}</span>
        </div>

        {/* upside bar */}
        {pick.upside_pct != null && (
          <div className="mb-2.5">
            <div className="flex justify-between items-center mb-1">
              <span className="text-[14px] text-muted-foreground/80 uppercase tracking-wider">Analyst Target</span>
              <span className="text-[15px] font-bold font-mono" style={{color:upsideColor}}>
                {upside>0?"+":""}{upside}% upside
              </span>
            </div>
            <div className="h-1 rounded-full overflow-hidden bg-muted">
              <div className="h-full rounded-full transition-all duration-500" style={{width:`${upsideBar}%`, background:`linear-gradient(to right,${upsideColor}80,${upsideColor})`}}/>
            </div>
          </div>
        )}

        {/* key stats row — show data we actually have from CSV */}
        <div className="grid grid-cols-3 gap-1.5">
          {(() => {
            const pe = pick.pe != null ? Number(pick.pe).toFixed(2) : undefined;
            const fwdPe = pick.forward_pe != null ? Number(pick.forward_pe).toFixed(2) : undefined;
            return [
              {label:"MCap", val:pick.market_cap},
              {label:pe ? "PE" : fwdPe ? "FWD PE" : "PE", val:pe ?? fwdPe},
              {label:"Beta", val:pick.beta != null ? Number(pick.beta).toFixed(2) : undefined},
            ].map(({label,val}) => (
              <div key={label} className="rounded-lg p-1.5 text-center bg-secondary">
                <div className="text-[8px] text-muted-foreground/80 mb-0.5">{label}</div>
                <div className={`text-[15px] font-mono font-bold ${val ? "text-foreground/80" : "text-muted-foreground/60"}`}>{val ?? "N/A"}</div>
              </div>
            ));
          })()}
        </div>
      </div>
    </div>
  );
}

/* ─── Research page ──────────────────────────────────────────────────────────── */

export function Research() {
  const [data, setData] = useState<WebTickerSentiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const [broad, setBroad] = useState<BroadSentiment | null>(null);
  const [broadLoading, setBroadLoading] = useState(true);

  const [picks, setPicks] = useState<StockPick[]>([]);
  const [spotlight, setSpotlight] = useState<StockPick[]>([]);
  const [grades, setGrades] = useState<Record<string, number>>({});
  const [picksLoading, setPicksLoading] = useState(true);
  const [shuffleSeed, setShuffleSeed] = useState(0);
  const [shuffling, setShuffling] = useState(false);

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);

  /* watchlist — localStorage */
  const [watchlist, setWatchlist] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("tt_watchlist") ?? "[]"); } catch { return []; }
  });
  const toggleWatchlist = (ticker: string) => {
    setWatchlist(prev => {
      const next = prev.includes(ticker) ? prev.filter(t => t !== ticker) : [...prev, ticker];
      localStorage.setItem("tt_watchlist", JSON.stringify(next));
      return next;
    });
  };
  const watchlistData = useMemo(() => {
    const all = [...picks, ...spotlight];
    return watchlist.map(t => all.find(p => p.ticker === t)).filter(Boolean) as StockPick[];
  }, [watchlist, picks, spotlight]);

  const [searchInput, setSearchInput] = useState("");
  const [searchError, setSearchError] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  const { data: prices } = useGetTickerPrices();

  /* market movers */
  const [movers, setMovers] = useState<MarketMover[]>([]);
  const [moversLoading, setMoversLoading] = useState(true);
  const fetchMovers = async () => {
    try {
      const res = await fetch(`${BASE}/api/market/movers?_=${Date.now()}`);
      const json = await res.json();
      setMovers(json.stocks || []);
    } catch { /* ignore */ } finally { setMoversLoading(false); }
  };

  /* fetch ranking data */
  const fetchRankings = async (spinner = false, extraTickers?: string[]) => {
    if (spinner) setRefreshing(true);
    try {
      const allTickers = Array.from(new Set([...(extraTickers ?? [])]));
      const url = allTickers.length
        ? `${BASE}/api/market/news-sentiment?tickers=${encodeURIComponent(allTickers.join(","))}&_=${Date.now()}`
        : `${BASE}/api/market/news-sentiment?_=${Date.now()}`;
      const res = await fetch(url);
      setData(await res.json());
      setLastFetched(new Date());
    } catch { /* keep stale */ } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  /* fetch broad market sentiment */
  const fetchBroad = async () => {
    try {
      const res = await fetch(`${BASE}/api/market/broad-sentiment?_=${Date.now()}`);
      setBroad(await res.json());
    } catch { /* ignore */ } finally { setBroadLoading(false); }
  };

  /* fetch daily picks — retries every 20s while scorer is warming up */
  const picksRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchPicks = async (attempt = 0, seed = 0) => {
    try {
      const url = seed > 0
        ? `${BASE}/api/stock/picks?shuffle=${seed}`
        : `${BASE}/api/stock/picks`;
      const res = await fetch(url);
      const json = await res.json();
      const list = Array.isArray(json) ? json : (json?.picks ?? []);
      if (list.length > 0) {
        setPicks(list);
        if (json?.spotlight) setSpotlight(json.spotlight);
        if (json?.grades) setGrades(json.grades);
        setPicksLoading(false);
        setShuffling(false);
        return;
      }
    } catch { /* ignore */ }
    // Picks empty or request failed — scorer may still be warming up
    if (attempt < 18) { // retry for up to ~6 min
      picksRetryRef.current = setTimeout(() => fetchPicks(attempt + 1, seed), 20_000);
    } else {
      setPicksLoading(false);
      setShuffling(false);
    }
  };

  const handleShuffle = () => {
    if (shuffling || picksLoading) return;
    const newSeed = Math.floor(Math.random() * 90000) + 1;
    setShuffleSeed(newSeed);
    setShuffling(true);
    setPicksLoading(true);
    if (picksRetryRef.current) clearTimeout(picksRetryRef.current);
    fetchPicks(0, newSeed);
  };

  useEffect(() => {
    fetchRankings();
    fetchBroad();
    fetchPicks();
    fetchMovers();
    const interval = setInterval(() => {
      fetchRankings();
      fetchBroad();
      fetchPicks(0, shuffleSeed);
      fetchMovers();
    }, 300_000); // auto-refresh every 5 minutes
    return () => {
      if (picksRetryRef.current) clearTimeout(picksRetryRef.current);
      clearInterval(interval);
    };
  }, []);

  /* Fetch sentiment for pick tickers when picks change */
  useEffect(() => {
    const pickTickers = picks.map(p => p.ticker);
    const spotTickers = spotlight.map(p => p.ticker);
    const allTickers = Array.from(new Set([...pickTickers, ...spotTickers]));
    if (allTickers.length === 0) return;
    fetch(`${BASE}/api/market/news-sentiment?tickers=${encodeURIComponent(allTickers.join(","))}`)
      .then(r => r.json())
      .then(d => {
        if (Array.isArray(d)) {
          setData(prev => {
            const prevArr = Array.isArray(prev) ? prev : [];
            const existing = new Map(prevArr.map(x => [x.ticker, x]));
            d.forEach(x => existing.set(x.ticker, x));
            return Array.from(existing.values());
          });
        }
      })
      .catch(() => {});
  }, [picks, spotlight]);

  const handleRefresh = () => { fetchRankings(true); fetchBroad(); fetchPicks(0, shuffleSeed); fetchMovers(); };

  const handleChip = useCallback((t: string) => {
    setSelectedTicker(prev => prev === t ? null : t);
    setSearchInput("");
    setSearchError("");
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const tk = searchInput.trim().toUpperCase().replace(/[^A-Z0-9.-^]/g,"");
    if (!tk) return;
    setSearchError("");
    setSelectedTicker(tk);
  };

  const clearSearch = () => {
    setSelectedTicker(null);
    setSearchInput("");
    setSearchError("");
  };

  const sentiment = selectedTicker ? data.find(d => d.ticker === selectedTicker) : undefined;

  const mktScore = useMemo(() => {
    if (!data.length) return null;
    const tot = data.reduce((s,d)=>s+d.article_count,0)||1;
    const wp  = data.reduce((s,d)=>s+(d.positive_pct/100)*d.article_count,0);
    return Math.round(wp/tot*100);
  }, [data]);

  return (
    <div className="flex flex-col h-full -m-6">
      {/* ── top bar ── */}
      <div className="px-6 py-4 border-b border-border bg-card/60 shrink-0">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-primary"/>
            <span className="text-sm font-bold uppercase tracking-widest">Research</span>
          </div>
          <div className="flex-1"/>
          {/* Search bar */}
          <form onSubmit={handleSearch} className="flex items-center gap-1.5 ml-auto">
            <div className="relative flex items-center">
              <Search className="w-3 h-3 absolute left-2 text-muted-foreground pointer-events-none"/>
              <input
                ref={searchRef}
                value={searchInput}
                onChange={e => setSearchInput(e.target.value.toUpperCase())}
                placeholder="Search ticker… AAPL"
                className="pl-6 pr-2 py-1 text-[14px] font-mono bg-muted/20 border border-border rounded focus:outline-none focus:border-primary/50 w-36 placeholder:text-muted-foreground"
              />
            </div>
            <button type="submit" className="text-[14px] px-2 py-1 rounded bg-primary/10 border border-primary/30 text-primary hover:bg-primary/10 transition-colors font-mono">GO</button>
            {selectedTicker && !data.find(d=>d.ticker===selectedTicker) && (
              <button type="button" onClick={clearSearch} className="text-muted-foreground hover:text-foreground">
                <X className="w-3.5 h-3.5"/>
              </button>
            )}
          </form>

          {lastFetched && <span className="text-[15px] text-muted-foreground">{lastFetched.toLocaleTimeString()}</span>}
          <button onClick={handleRefresh} disabled={refreshing||loading}
            className="flex items-center gap-1.5 text-[14px] text-muted-foreground hover:text-foreground disabled:opacity-40">
            <RefreshCw className={`w-3 h-3 ${refreshing?"animate-spin":""}`}/>
            {refreshing?"Fetching…":"Refresh"}
          </button>
        </div>

        {searchError && <span className="text-[15px] text-[#dc2626] self-center mt-2">{searchError}</span>}
      </div>

      {/* ── main area ── */}
      <div className="flex-1 overflow-hidden">
        {selectedTicker ? (
          <StockDetail ticker={selectedTicker} sentiment={sentiment} broad={broad} onBack={()=>setSelectedTicker(null)}/>
        ) : (
          <div className="grid grid-cols-[1fr_340px] h-full">

            {/* LEFT — Rankings + Picks */}
            <div className="border-r border-border overflow-y-auto">

              {/* Daily Picks */}
              <div className="p-6 border-b border-border">
                <div className="flex items-center gap-2 mb-3">
                  <Star className="w-3.5 h-3.5 text-primary"/>
                  <span className="text-[14px] font-bold uppercase tracking-widest text-[#4a3b8c]">AI Daily Picks</span>
                  <span className="text-[14px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-mono border border-primary/30">10 large cap · fresh picks</span>
                  <button
                    onClick={handleShuffle}
                    disabled={shuffling || picksLoading}
                    title="Shuffle — pick a fresh set"
                    className="ml-auto flex items-center gap-1.5 text-[15px] tracking-widest uppercase px-2.5 py-1 border border-primary/30 text-primary/70 hover:text-primary hover:border-primary/60 hover:bg-primary/10 disabled:opacity-40 disabled:cursor-not-allowed transition-all rounded"
                  >
                    <RefreshCw className={`w-3 h-3 ${shuffling ? "animate-spin" : ""}`}/>
                    {shuffling ? "Scoring…" : "Shuffle"}
                  </button>
                </div>
                <div className="flex items-center gap-2 mb-4">
                  <div className="text-[15px] text-muted-foreground">
                    Pure fundamentals
                  </div>
                </div>

                {picksLoading ? (
                  <div className="grid grid-cols-2 gap-4">
                    {Array.from({length:10}).map((_,i)=><Skeleton key={i} className="h-44 rounded-2xl"/>)}
                  </div>
                ) : picks.length === 0 ? (
                  <div className="flex items-center gap-2 text-[14px] text-muted-foreground p-4 border border-border/40 rounded-lg">
                    <RefreshCw className="w-3 h-3 animate-spin shrink-0"/>
                    Scoring 69 stocks in background — ready in ~60s after a fresh deploy
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    {picks.map((p,i) => {
                      const pSent = Math.round((Array.isArray(data) ? data.find(d=>d.ticker===p.ticker) : undefined)?.positive_pct ?? 50);
                      const pGrade = grades[p.ticker] ?? p.grade_score;
                      const pComp = Math.round(pSent * 0.2 + pGrade * 0.8);
                      return <PickCard key={p.ticker} pick={p} rank={i+1} compositeScore={pComp} onClick={()=>handleChip(p.ticker)} watchlist={watchlist} onToggleWatchlist={toggleWatchlist}/>;
                    })}
                  </div>
                )}
              </div>

              {/* Small & Mid Cap Spotlight */}
              <div className="p-6 border-b border-border">
                <div className="flex items-center gap-2 mb-3">
                  <Zap className="w-3.5 h-3.5 text-[#7C5CFC]"/>
                  <span className="text-[14px] font-bold uppercase tracking-widest text-[#7C5CFC]">Small & Mid Cap Spotlight</span>
                  <span className="text-[14px] bg-[#7C5CFC]/10 text-[#7C5CFC] px-1.5 py-0.5 rounded font-mono border border-[#7C5CFC]/30">6 picks · refreshed every 2h</span>
                </div>
                <p className="text-[15px] text-muted-foreground/80 mb-4">High-growth small &amp; mid-cap names scored by the same fundamentals algorithm</p>
                {picksLoading ? (
                  <div className="grid grid-cols-2 gap-4">
                    {Array.from({length:6}).map((_,i)=><Skeleton key={i} className="h-44 rounded-2xl"/>)}
                  </div>
                ) : spotlight.length === 0 ? (
                  <div className="flex items-center gap-2 text-[14px] text-muted-foreground p-4 border border-border/40 rounded-lg">
                    <RefreshCw className="w-3 h-3 animate-spin shrink-0"/>
                    Scoring small &amp; mid cap pool…
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    {spotlight.map((p,i) => {
                      const pSent = Math.round((Array.isArray(data) ? data.find(d=>d.ticker===p.ticker) : undefined)?.positive_pct ?? 50);
                      const pGrade = grades[p.ticker] ?? p.grade_score;
                      const pComp = Math.round(pSent * 0.2 + pGrade * 0.8);
                      return <PickCard key={p.ticker} pick={p} rank={i+1} compositeScore={pComp} onClick={()=>handleChip(p.ticker)} watchlist={watchlist} onToggleWatchlist={toggleWatchlist}/>;
                    })}
                  </div>
                )}
              </div>

            </div>

            {/* RIGHT — Broad Sentiment + Guide */}
            <div className="p-4 space-y-4 overflow-y-auto bg-card/20">

              {/* Broad Market Sentiment */}
              <div className="border border-border rounded-lg p-4 bg-card space-y-3">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-3.5 h-3.5 text-primary"/>
                  <span className="text-[14px] font-bold uppercase tracking-widest text-[#4a3b8c]">Market Sentiment</span>
                </div>
                {broadLoading || !broad ? (
                  <div className="space-y-2"><Skeleton className="h-12 w-24"/><Skeleton className="h-3 w-full"/></div>
                ) : (
                  <>
                    <div className="flex items-end gap-2">
                      <span className="text-4xl font-bold font-mono" style={{color:heatColor(broad.score)}}>{broad.score}</span>
                      <span className="text-muted-foreground text-sm mb-1">/ 100</span>
                    </div>
                    <div className="relative h-3 rounded-full overflow-hidden bg-muted/20">
                      <div className="absolute inset-0 rounded-full opacity-25" style={{background:"linear-gradient(to right,#dc2626,#ea580c,#d97706,#7a9e2a,#006400)"}}/>
                      <div className="h-full rounded-full transition-all" style={{width:`${broad.score}%`,backgroundColor:heatColor(broad.score)}}/>
                    </div>
                    <div className="flex justify-between text-[14px] text-muted-foreground">
                      <span>0 Bearish</span><span>50 Neutral</span><span>100 Bullish</span>
                    </div>
                    <div className="text-[14px]" style={{color:heatColor(broad.score)}}>
                      <span className="font-bold">{heatLabel(broad.score)}</span>
                    </div>
                    <div className="pt-1 border-t border-border/50 grid grid-cols-3 gap-2 text-center">
                      {[
                        {label:"Positive",val:broad.positive_count,color:"#7a9e2a"},
                        {label:"Neutral",val:broad.neutral_count,color:"#d97706"},
                        {label:"Negative",val:broad.negative_count,color:"#dc2626"},
                      ].map(({label,val,color})=>(
                        <div key={label}>
                          <div className="text-[14px] text-muted-foreground">{label}</div>
                          <div className="font-sans font-bold text-sm" style={{color}}>{val}</div>
                        </div>
                      ))}
                    </div>
                    <div className="text-[15px] text-muted-foreground">
                      From <span className="text-foreground font-bold">{broad.total_articles}</span> articles across{" "}
                      <span className="text-foreground font-bold">20</span> market ETFs &amp; indices
                    </div>

                    {/* Top macro headlines */}
                    {broad.top_headlines?.length > 0 && (
                      <MacroHeadlines headlines={broad.top_headlines}/>
                    )}
                  </>
                )}
              </div>

              {/* How picks are scored */}
              <div className="border border-border rounded-lg p-4 bg-card space-y-2">
                <div className="flex items-center gap-2">
                  <Star className="w-3.5 h-3.5 text-primary"/>
                  <span className="text-[14px] font-bold uppercase tracking-widest text-muted-foreground">Pick Scoring</span>
                </div>
                <div className="space-y-1.5 text-[15px] text-muted-foreground">
                  {[
                    {label:"Analyst Consensus",pts:"20 pts"},
                    {label:"Profit Margin",pts:"20 pts"},
                    {label:"Revenue Growth",pts:"15 pts"},
                    {label:"Analyst Upside",pts:"15 pts"},
                    {label:"Valuation (P/E + EV)",pts:"15 pts"},
                    {label:"Total Debt (D/E)",pts:"10 pts"},
                    {label:"Free Cash Flow",pts:"10 pts"},
                  ].map(({label,pts})=>(
                    <div key={label} className="flex justify-between">
                      <span>{label}</span>
                      <span className="text-primary font-mono">{pts}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Watchlist */}
              {watchlist.length > 0 && (
                <div className="border border-border rounded-lg p-4 bg-card space-y-2">
                  <div className="flex items-center gap-2">
                    <Bookmark className="w-3.5 h-3.5 text-primary"/>
                    <span className="text-[14px] font-bold uppercase tracking-widest text-muted-foreground">Watchlist</span>
                    <span className="text-[14px] text-muted-foreground ml-auto">{watchlist.length}</span>
                  </div>
                  <div className="space-y-1">
                    {watchlistData.map(p => (
                      <div key={p.ticker} className="flex items-center justify-between text-[15px] cursor-pointer hover:bg-muted/30 rounded px-1 py-0.5" onClick={() => handleChip(p.ticker)}>
                        <span className="font-mono font-bold">${p.ticker}</span>
                        <span className={p.change_pct && p.change_pct >= 0 ? "text-[#006400]" : "text-[#dc2626]"}>{p.change_pct ? `${p.change_pct >= 0 ? "+" : ""}${(p.change_pct * 100).toFixed(2)}%` : "N/A"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top Movers */}
              <TopMovers stocks={movers} onClick={handleChip} loading={moversLoading}/>

            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export { Research as Stocks };
