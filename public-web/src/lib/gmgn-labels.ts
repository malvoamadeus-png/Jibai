import { getGmgnLabelApiUrl } from "@/lib/env";

export type GMGNChain = {
  key: string;
  label: string;
  chainIndex: string;
  isEvm: boolean;
};

export type GMGNWalletRank = {
  holderWalletAddress: string;
  rank: number;
};

export type GMGNTokenResult = {
  inputToken: string;
  tokenAddress: string;
  chain: GMGNChain;
  ticker: string;
  topHolders: GMGNWalletRank[];
  topTraders: GMGNWalletRank[];
};

export type GMGNTokenError = {
  inputToken: string;
  message: string;
};

export type GMGNLabelsResponse = {
  results: GMGNTokenResult[];
  errors: GMGNTokenError[];
};

export type GMGNLabelEntry = {
  address: string;
  rename: string;
  emoji: string;
};

type RankedWallet = {
  address: string;
  holderRank: number | null;
  traderRank: number | null;
};

export function parseTokenInput(value: string) {
  const seen = new Set<string>();
  const tokens: string[] = [];
  for (const raw of value.split(/\r?\n/)) {
    const token = raw.trim();
    const key = token.toLowerCase();
    if (!token || seen.has(key)) continue;
    seen.add(key);
    tokens.push(token);
  }
  return tokens;
}

function normalizeAddress(value: unknown, isEvm: boolean) {
  const text = String(value || "").trim();
  return isEvm ? text.toLowerCase() : text;
}

export function parseExistingAddressSet(value: string, isEvm: boolean) {
  const text = value.trim();
  if (!text) return new Set<string>();

  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : "JSON 解析失败");
  }

  if (!Array.isArray(payload)) {
    throw new Error("备注内容必须是 JSON 数组");
  }

  const addresses = new Set<string>();
  for (const item of payload) {
    if (!item || typeof item !== "object" || !("address" in item)) continue;
    const address = normalizeAddress((item as { address?: unknown }).address, isEvm);
    if (address) addresses.add(address);
  }
  return addresses;
}

function sanitizeTicker(value: unknown) {
  return String(value || "").trim().replace(/\s+/g, "").toUpperCase();
}

function rankNumber(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function sortRank(value: number | null) {
  return value ?? Number.MAX_SAFE_INTEGER;
}

function mergeWalletRanks(result: GMGNTokenResult) {
  const merged = new Map<string, RankedWallet>();
  for (const row of result.topHolders || []) {
    const address = normalizeAddress(row.holderWalletAddress, result.chain.isEvm);
    if (!address) continue;
    const item = merged.get(address) || { address, holderRank: null, traderRank: null };
    item.holderRank = rankNumber(row.rank);
    merged.set(address, item);
  }
  for (const row of result.topTraders || []) {
    const address = normalizeAddress(row.holderWalletAddress, result.chain.isEvm);
    if (!address) continue;
    const item = merged.get(address) || { address, holderRank: null, traderRank: null };
    item.traderRank = rankNumber(row.rank);
    merged.set(address, item);
  }
  return [...merged.values()].sort((left, right) => {
    const leftBest = Math.min(sortRank(left.holderRank), sortRank(left.traderRank));
    const rightBest = Math.min(sortRank(right.holderRank), sortRank(right.traderRank));
    return (
      leftBest - rightBest ||
      sortRank(left.holderRank) - sortRank(right.holderRank) ||
      sortRank(left.traderRank) - sortRank(right.traderRank) ||
      left.address.localeCompare(right.address)
    );
  });
}

function buildRename(ticker: string, holderRank: number | null, traderRank: number | null) {
  const parts = [sanitizeTicker(ticker)];
  if (holderRank) parts.push(`持${holderRank}`);
  if (traderRank) parts.push(`盈${traderRank}`);
  return parts.join("");
}

function buildNewLabelEntries(results: GMGNTokenResult[], existing: Set<string>, isEvm: boolean) {
  const seenNew = new Set<string>();
  const output: GMGNLabelEntry[] = [];
  for (const result of results) {
    for (const row of mergeWalletRanks(result)) {
      const address = normalizeAddress(row.address, isEvm);
      if (!address || existing.has(address) || seenNew.has(address)) continue;
      const rename = buildRename(result.ticker, row.holderRank, row.traderRank);
      if (!rename) continue;
      output.push({ address, rename, emoji: "" });
      seenNew.add(address);
    }
  }
  return output;
}

export function buildLocalGMGNLabels(results: GMGNTokenResult[], evmExistingText: string, solExistingText: string) {
  const evmExisting = parseExistingAddressSet(evmExistingText, true);
  const solExisting = parseExistingAddressSet(solExistingText, false);
  const evmResults = results.filter((result) => result.chain.isEvm);
  const solResults = results.filter((result) => !result.chain.isEvm);
  return {
    evm: buildNewLabelEntries(evmResults, evmExisting, true),
    solana: buildNewLabelEntries(solResults, solExisting, false),
  };
}

export function formatLabelEntries(entries: GMGNLabelEntry[]) {
  return JSON.stringify(entries, null, 4);
}

export async function fetchGMGNLabels(tokens: string[], limit: number, accessToken: string): Promise<GMGNLabelsResponse> {
  const response = await fetch(`${getGmgnLabelApiUrl()}/api/onchain/gmgn-labels`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ tokens, limit }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "GMGN 备注生成接口请求失败";
    throw new Error(detail);
  }
  return payload as GMGNLabelsResponse;
}
