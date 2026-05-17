"use client";

import type { OnchainChain, OnchainChainKey } from "@/lib/types";

export const ONCHAIN_CHAINS: Array<{ key: OnchainChainKey; label: string }> = [
  { key: "ethereum", label: "ETH" },
  { key: "base", label: "Base" },
  { key: "bsc", label: "BSC" },
  { key: "solana", label: "Solana" },
];

export function chainLabel(key: string) {
  return ONCHAIN_CHAINS.find((item) => item.key === key)?.label || key;
}

export function ChainBadge({ chain }: { chain: string }) {
  return <span className={`chain-badge chain-${chain}`}>{chainLabel(chain)}</span>;
}

export function ChainFilter({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  function toggle(key: string) {
    onChange(value.includes(key) ? value.filter((item) => item !== key) : [...value, key]);
  }

  return (
    <div className="chain-filter" aria-label="链筛选">
      {ONCHAIN_CHAINS.map((chain) => (
        <button
          key={chain.key}
          className={value.includes(chain.key) ? "chain-filter-item active" : "chain-filter-item"}
          type="button"
          onClick={() => toggle(chain.key)}
        >
          {chain.label}
        </button>
      ))}
    </div>
  );
}

export function formatUsd(value: number | null | undefined) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "-";
  if (Math.abs(num) >= 1000000) return `$${(num / 1000000).toFixed(2)}M`;
  if (Math.abs(num) >= 1000) return `$${(num / 1000).toFixed(1)}K`;
  return `$${num.toFixed(0)}`;
}

export function formatTokenAmount(value: number | null | undefined) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "-";
  if (num === 0) return "0";
  if (Math.abs(num) >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
  if (Math.abs(num) >= 1000) return `${(num / 1000).toFixed(1)}K`;
  if (Math.abs(num) >= 1) return num.toFixed(2);
  return num.toPrecision(3);
}

export function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

export function chainSummary(chains: OnchainChain[]) {
  return chains.map((chain) => chainLabel(chain.key)).join("、") || "-";
}

export function runStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
    success: "成功",
    empty: "空结果",
    api_error: "API 错误",
    rate_limited: "限流",
    auth_error: "鉴权错误",
    network_error: "网络错误",
    partial: "部分成功",
    new: "新增",
    held: "持有",
    increased: "增持",
    decreased: "减持",
    exited: "退出",
    below_threshold: "低于阈值",
  };
  return labels[status] || status || "-";
}
