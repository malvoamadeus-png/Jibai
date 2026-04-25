import "server-only";

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { z } from "zod";

import { getDb } from "@/lib/db";
import { getLocalProjectPaths } from "@/lib/local-paths";
import { entityAuthorViewSchema } from "@/lib/schemas";
import { getServerEnv } from "@/lib/server-env";
import type {
  EntityAuthorView,
  StockKlineCandle,
  StockKlineData,
  StockKlineMarker,
} from "@/lib/types";

type StockIdentity = {
  securityKey: string;
  displayName: string;
  ticker: string | null;
  market: string | null;
};

type ChartProviderResult = {
  sourceLabel: string | null;
  message: string | null;
  candles: StockKlineCandle[];
};

const execFileAsync = promisify(execFile);
const markerSchema = z.array(entityAuthorViewSchema);
const A_SHARE_MARKETS = new Set(["SSE", "SZSE", "BJSE"]);
const TWELVE_DATA_EXCHANGE_MAP: Record<string, string> = {
  NASDAQ: "NASDAQ",
  NYSE: "NYSE",
  AMEX: "AMEX",
  LSE: "LSE",
  XETRA: "XETRA",
  EPA: "EPA",
  EBR: "EBR",
  XMIL: "XMIL",
  SIX: "SIX",
  EURONEXT: "EURONEXT",
  KRX: "KRX",
  KOSDAQ: "KOSDAQ",
  TSX: "TSX",
  TSXV: "TSXV",
};
const YAHOO_FINANCE_SUFFIX_MAP: Record<string, string> = {
  NASDAQ: "",
  NYSE: "",
  AMEX: "",
  LSE: ".L",
  XETRA: ".DE",
  EPA: ".PA",
  EBR: ".BR",
  XMIL: ".MI",
  SIX: ".SW",
  KRX: ".KS",
  KOSDAQ: ".KQ",
  TSX: ".TO",
  TSXV: ".V",
};

function parseJson<T>(raw: string, schema: z.ZodType<T>, fallback: T) {
  try {
    return schema.parse(JSON.parse(raw));
  } catch {
    return fallback;
  }
}

function toNumber(value: string | number | null | undefined) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function inferAshareMarket(identity: StockIdentity) {
  const normalizedMarket = (identity.market ?? "").toUpperCase();
  if (A_SHARE_MARKETS.has(normalizedMarket)) {
    return normalizedMarket;
  }
  if (identity.securityKey.endsWith(".sh")) return "SSE";
  if (identity.securityKey.endsWith(".sz")) return "SZSE";
  if (identity.securityKey.endsWith(".bj")) return "BJSE";
  return null;
}

function resolveTicker(identity: StockIdentity) {
  const normalizedTicker = (identity.ticker ?? "").trim().toUpperCase();
  if (normalizedTicker) {
    return normalizedTicker;
  }
  const match = identity.securityKey.match(/^(\d{6})\.(?:sh|sz|bj)$/i);
  if (match) {
    return match[1];
  }
  if (/^[A-Z][A-Z0-9.]{0,9}$/i.test(identity.securityKey)) {
    return identity.securityKey.toUpperCase();
  }
  return null;
}

function isAshare(identity: StockIdentity) {
  return Boolean(inferAshareMarket(identity) && /^\d{6}$/.test(resolveTicker(identity) ?? ""));
}

function toYahooSymbol(identity: StockIdentity) {
  const ticker = resolveTicker(identity);
  if (!ticker) {
    return null;
  }

  const normalizedMarket = (identity.market ?? "").trim().toUpperCase();
  const suffix = normalizedMarket ? YAHOO_FINANCE_SUFFIX_MAP[normalizedMarket] : undefined;
  if (suffix !== undefined) {
    return `${ticker}${suffix}`;
  }

  if (/[.-]/.test(ticker)) {
    return ticker;
  }

  if (/^[A-Z0-9.-]{1,20}$/i.test(identity.securityKey)) {
    return identity.securityKey.toUpperCase();
  }

  return ticker;
}

function getMarkerRows(securityKey: string, dateFrom: string | null) {
  const db = getDb();
  if (!db) {
    return [];
  }

  const rows = db
    .prepare(
      `
      SELECT
        sdv.date_key AS date,
        sdv.mention_count AS mentionCount,
        sdv.author_views_json AS authorViewsJson
      FROM security_daily_views sdv
      JOIN security_entities se ON se.id = sdv.security_id
      WHERE se.security_key = ?
      ${dateFrom ? "AND sdv.date_key >= ?" : ""}
      ORDER BY sdv.date_key ASC
      `,
    )
    .all(...(dateFrom ? [securityKey, dateFrom] : [securityKey])) as Array<{
    date: string;
    mentionCount: number;
    authorViewsJson: string;
  }>;

  return rows.map(
    (row): StockKlineMarker => ({
      date: row.date,
      mentionCount: row.mentionCount,
      authorViews: parseJson(row.authorViewsJson, markerSchema, []).map(
        (item): EntityAuthorView => ({
          platform: item.platform ?? "",
          account_name: item.account_name,
          author_nickname: item.author_nickname ?? "",
          stance: item.stance,
          logic: item.logic ?? "",
          note_ids: item.note_ids ?? [],
          note_urls: item.note_urls ?? [],
          evidence: item.evidence ?? [],
          time_horizons: item.time_horizons ?? [],
        }),
      ),
    }),
  );
}

async function fetchJson(url: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);

  try {
    const response = await fetch(url, {
      headers: {
        accept: "application/json",
        "user-agent": "Mozilla/5.0",
      },
      next: { revalidate: 60 * 60 * 4 },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchEastMoneyCandles(identity: StockIdentity, days: number): Promise<ChartProviderResult> {
  const ticker = resolveTicker(identity);
  const market = inferAshareMarket(identity);
  if (!ticker || !market) {
    return {
      sourceLabel: "东财",
      message: "当前标的缺少可用于东财查询的 A 股代码。",
      candles: [],
    };
  }

  try {
    const { rootDir } = getLocalProjectPaths();
    const pythonExecutable = process.env.PYTHON_EXECUTABLE || "python";
    const script = `
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
backend_dir = root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from packages.common.market_data import fetch_eastmoney_daily

result = fetch_eastmoney_daily(
    ticker=sys.argv[2],
    market=sys.argv[3],
    days=int(sys.argv[4]),
)
print(json.dumps(result, ensure_ascii=False))
`.trim();
    const { stdout } = await execFileAsync(
      pythonExecutable,
      ["-c", script, rootDir, ticker, market, String(days)],
      {
        maxBuffer: 1024 * 1024,
        timeout: 12_000,
        windowsHide: true,
      },
    );
    return JSON.parse(stdout.trim()) as ChartProviderResult;
  } catch (error) {
    return {
      sourceLabel: "东财",
      message: `东财日线获取失败：${error instanceof Error ? error.message : "unknown error"}`,
      candles: [],
    };
  }
}

async function fetchTwelveDataCandles(identity: StockIdentity, days: number): Promise<ChartProviderResult> {
  const apiKey = getServerEnv("TWELVE_DATA_API_KEY") ?? getServerEnv("TWELVEDATA_API_KEY");
  if (!apiKey) {
    return {
      sourceLabel: "Twelve Data",
      message: "未配置 TWELVE_DATA_API_KEY，当前仅 A 股可直接显示日线。",
      candles: [],
    };
  }

  const ticker = resolveTicker(identity);
  if (!ticker) {
    return {
      sourceLabel: "Twelve Data",
      message: "当前标的缺少可用于全球行情查询的 ticker。",
      candles: [],
    };
  }

  const params = new URLSearchParams({
    symbol: ticker,
    interval: "1day",
    outputsize: String(Math.max(30, Math.min(days, 5000))),
    order: "asc",
    apikey: apiKey,
  });

  const exchange = identity.market ? TWELVE_DATA_EXCHANGE_MAP[identity.market.toUpperCase()] : null;
  if (exchange) {
    params.set("exchange", exchange);
  }

  try {
    const payload = (await fetchJson(
      `https://api.twelvedata.com/time_series?${params.toString()}`,
    )) as {
      status?: string;
      message?: string;
      values?: Array<{
        datetime?: string;
        open?: string;
        high?: string;
        low?: string;
        close?: string;
        volume?: string;
      }>;
    };

    if (payload.status === "error") {
      return {
        sourceLabel: "Twelve Data",
        message: payload.message || "全球日线接口返回错误。",
        candles: [],
      };
    }

    const candles = (payload.values ?? [])
      .map((item) => {
        const open = toNumber(item.open);
        const high = toNumber(item.high);
        const low = toNumber(item.low);
        const close = toNumber(item.close);
        const volume = toNumber(item.volume);
        if (!item.datetime || open === null || high === null || low === null || close === null) {
          return null;
        }
        return {
          date: item.datetime.slice(0, 10),
          open,
          high,
          low,
          close,
          volume,
        } satisfies StockKlineCandle;
      })
      .filter((item): item is StockKlineCandle => item !== null)
      .sort((left, right) => left.date.localeCompare(right.date));

    return {
      sourceLabel: "Twelve Data",
      message: candles.length > 0 ? null : "全球行情源没有返回这只股票的日线数据。",
      candles,
    };
  } catch (error) {
    return {
      sourceLabel: "Twelve Data",
      message: `全球日线获取失败：${error instanceof Error ? error.message : "unknown error"}`,
      candles: [],
    };
  }
}

async function fetchYahooFinanceCandles(identity: StockIdentity, days: number): Promise<ChartProviderResult> {
  const symbol = toYahooSymbol(identity);
  if (!symbol) {
    return {
      sourceLabel: "Yahoo Finance",
      message: "当前标的缺少可用于 Yahoo Finance 查询的 ticker。",
      candles: [],
    };
  }

  try {
    const { rootDir } = getLocalProjectPaths();
    const pythonExecutable = process.env.PYTHON_EXECUTABLE || "python";
    const script = `
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
backend_dir = root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from packages.common.market_data import fetch_yahoo_daily

result = fetch_yahoo_daily(
    symbol=sys.argv[2],
    days=int(sys.argv[3]),
)
print(json.dumps(result, ensure_ascii=False))
`.trim();
    const { stdout } = await execFileAsync(
      pythonExecutable,
      ["-c", script, rootDir, symbol, String(days)],
      {
        maxBuffer: 1024 * 1024,
        timeout: 12_000,
        windowsHide: true,
      },
    );
    return JSON.parse(stdout.trim()) as ChartProviderResult;
  } catch (error) {
    return {
      sourceLabel: "Yahoo Finance",
      message: `Yahoo Finance 日线获取失败：${error instanceof Error ? error.message : "unknown error"}`,
      candles: [],
    };
  }
}

async function fetchSinaCandles(identity: StockIdentity, days: number): Promise<ChartProviderResult> {
  const ticker = resolveTicker(identity);
  const market = inferAshareMarket(identity);
  if (!ticker || !market) {
    return {
      sourceLabel: "新浪",
      message: "当前标的缺少可用于新浪查询的 A 股代码。",
      candles: [],
    };
  }

  const prefix = market === "SSE" ? "sh" : market === "SZSE" ? "sz" : "bj";
  const payload = (await fetchJson(
    `https://quotes.sina.cn/cn/api/openapi.php/CN_MarketDataService.getKLineData?symbol=${prefix}${ticker}&scale=240&ma=no&datalen=${Math.max(30, Math.min(days, 1023))}`,
  )) as {
    result?: {
      status?: { code?: number };
      data?: Array<{
        day?: string;
        open?: string;
        high?: string;
        low?: string;
        close?: string;
        volume?: string;
      }>;
    };
  };

  const candles = (payload.result?.data ?? [])
    .map((item) => {
      const open = toNumber(item.open);
      const high = toNumber(item.high);
      const low = toNumber(item.low);
      const close = toNumber(item.close);
      const volume = toNumber(item.volume);
      if (!item.day || open === null || high === null || low === null || close === null) {
        return null;
      }
      return {
        date: item.day,
        open,
        high,
        low,
        close,
        volume,
      } satisfies StockKlineCandle;
    })
    .filter((item): item is StockKlineCandle => item !== null)
    .sort((left, right) => left.date.localeCompare(right.date));

  return {
    sourceLabel: "新浪",
    message: candles.length > 0 ? null : "新浪没有返回这只股票的日线数据。",
    candles,
  };
}

async function fetchAshareCandles(identity: StockIdentity, days: number): Promise<ChartProviderResult> {
  const eastMoneyResult = await fetchEastMoneyCandles(identity, days);
  if (eastMoneyResult.candles.length > 0) {
    return eastMoneyResult;
  }

  try {
    const sinaResult = await fetchSinaCandles(identity, days);
    if (sinaResult.candles.length > 0) {
      return {
        sourceLabel: sinaResult.sourceLabel,
        message: eastMoneyResult.message
          ? `东财当前不可用，已自动切换到新浪日线。`
          : sinaResult.message,
        candles: sinaResult.candles,
      };
    }
    return {
      sourceLabel: sinaResult.sourceLabel,
      message: eastMoneyResult.message || sinaResult.message,
      candles: sinaResult.candles,
    };
  } catch (error) {
    return {
      sourceLabel: "东财 / 新浪",
      message: eastMoneyResult.message || `A 股日线获取失败：${error instanceof Error ? error.message : "unknown error"}`,
      candles: [],
    };
  }
}

async function fetchGlobalCandles(identity: StockIdentity, days: number): Promise<ChartProviderResult> {
  const yahooResult = await fetchYahooFinanceCandles(identity, days);
  if (yahooResult.candles.length > 0) {
    return yahooResult;
  }

  const twelveResult = await fetchTwelveDataCandles(identity, days);
  if (twelveResult.candles.length > 0) {
    return {
      sourceLabel: twelveResult.sourceLabel,
      message: yahooResult.message
        ? "Yahoo Finance 当前不可用，已自动切换到 Twelve Data。"
        : twelveResult.message,
      candles: twelveResult.candles,
    };
  }

  const twelveNeedsApiKey = (twelveResult.message ?? "").includes("TWELVE_DATA_API_KEY");
  return {
    sourceLabel: yahooResult.sourceLabel || twelveResult.sourceLabel,
    message: twelveNeedsApiKey ? yahooResult.message : twelveResult.message || yahooResult.message,
    candles: [],
  };
}

export async function getStockKlineData(
  identity: StockIdentity,
  days = 180,
): Promise<StockKlineData> {
  const providerResult = isAshare(identity)
    ? await fetchAshareCandles(identity, days)
    : await fetchGlobalCandles(identity, days);

  const dateFrom = providerResult.candles[0]?.date ?? null;
  const markers = getMarkerRows(identity.securityKey, dateFrom);

  return {
    sourceLabel: providerResult.sourceLabel,
    message: providerResult.message,
    candles: providerResult.candles,
    markers,
  };
}
