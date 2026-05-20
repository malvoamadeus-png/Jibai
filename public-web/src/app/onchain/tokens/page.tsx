"use client";

import { useEffect, useMemo, useState } from "react";

import { ChainBadge, ChainFilter, formatTokenAmount, formatUsd } from "@/components/onchain-shared";
import { LoadingPanel } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { getOnchainTokenMatrix } from "@/lib/direct-data";
import type { OnchainTokenMatrixData } from "@/lib/types";

type Metric = "balance" | "value";
type SortMetric = "holders" | "balance" | "value";
type SortDirection = "asc" | "desc";
type SortKey = `${SortMetric}_${SortDirection}`;

function sortMetricValue(cell: OnchainTokenMatrixData["cells"][number] | undefined, metric: SortMetric) {
  if (!cell) return Number.NEGATIVE_INFINITY;
  if (metric === "holders") return cell.holderCount;
  if (metric === "balance") return cell.balanceSum;
  return cell.valueUsdSum;
}

export default function OnchainTokensPage() {
  const { loading, supabase } = useAuth();
  const [data, setData] = useState<OnchainTokenMatrixData | null>(null);
  const [metric, setMetric] = useState<Metric>("value");
  const [sortKey, setSortKey] = useState<SortKey>("value_desc");
  const [chainFilter, setChainFilter] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    getOnchainTokenMatrix(supabase, null, chainFilter)
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "代币矩阵加载失败"));
  }, [chainFilter, loading, supabase]);

  const cellMap = useMemo(() => {
    const map = new Map<string, OnchainTokenMatrixData["cells"][number]>();
    for (const cell of data?.cells || []) {
      map.set(`${cell.tokenId}:${cell.date}`, cell);
    }
    return map;
  }, [data]);

  const sortedTokens = useMemo(() => {
    const tokens = [...(data?.tokens || [])];
    const latestDate = data?.dates?.[data.dates.length - 1] || null;
    const [sortMetric, sortDirection] = sortKey.split("_") as [SortMetric, SortDirection];
    const directionFactor = sortDirection === "asc" ? 1 : -1;

    tokens.sort((left, right) => {
      const leftCell = latestDate ? cellMap.get(`${left.tokenId}:${latestDate}`) : undefined;
      const rightCell = latestDate ? cellMap.get(`${right.tokenId}:${latestDate}`) : undefined;
      const diff = sortMetricValue(leftCell, sortMetric) - sortMetricValue(rightCell, sortMetric);
      if (diff !== 0) return diff * directionFactor;
      return (left.displayName || left.symbol || left.tokenKey).localeCompare(
        right.displayName || right.symbol || right.tokenKey,
        "zh-CN",
      );
    });

    return tokens;
  }, [cellMap, data, sortKey]);

  if (loading) return <LoadingPanel />;

  function valueFor(cell: OnchainTokenMatrixData["cells"][number] | undefined) {
    if (!cell) return "-";
    const primaryValue = metric === "balance" ? formatTokenAmount(cell.balanceSum) : formatUsd(cell.valueUsdSum);
    return `${primaryValue}（${cell.holderCount}）`;
  }

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>按代币</h1>
          <p className="muted">Token 为行、日期为列，按持有数量或金额观察变化，并在括号里显示当天持有人数。</p>
        </div>
      </div>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}

      <section className="panel">
        <div className="filter-row">
          <button
            className={metric === "balance" ? "primary-button" : "secondary-button"}
            type="button"
            onClick={() => setMetric("balance")}
          >
            数量
          </button>
          <button
            className={metric === "value" ? "primary-button" : "secondary-button"}
            type="button"
            onClick={() => setMetric("value")}
          >
            金额
          </button>
          <label className="field" style={{ minWidth: 220 }}>
            <span>排序</span>
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
              <option value="holders_desc">持有人数降序</option>
              <option value="holders_asc">持有人数升序</option>
              <option value="balance_desc">数量降序</option>
              <option value="balance_asc">数量升序</option>
              <option value="value_desc">金额降序</option>
              <option value="value_asc">金额升序</option>
            </select>
          </label>
          <ChainFilter value={chainFilter} onChange={setChainFilter} />
        </div>
      </section>

      <section className="table-panel onchain-matrix" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>Token</th>
              {(data?.dates || []).map((date) => (
                <th key={date}>{date.slice(5)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedTokens.map((token) => (
              <tr key={token.tokenId}>
                <td>
                  <div className="account-cell">
                    <strong>{token.displayName || token.symbol || token.tokenKey}</strong>
                    <span className="muted">
                      <ChainBadge chain={token.chainKey} /> {token.symbol || token.contractAddress || "native"}
                    </span>
                  </div>
                </td>
                {(data?.dates || []).map((date) => {
                  const cell = cellMap.get(`${token.tokenId}:${date}`);
                  const delta = metric === "balance" ? cell?.balanceDelta : cell?.valueUsdDelta;
                  return (
                    <td key={date} className={delta && delta > 0 ? "delta-up" : delta && delta < 0 ? "delta-down" : ""}>
                      {valueFor(cell)}
                    </td>
                  );
                })}
              </tr>
            ))}
            {data?.tokens?.length ? (
              <tr>
                <td colSpan={(data?.dates.length || 0) + 1}>
                  <div className="empty">
                    括号里的数字表示当天持有该代币的地址数；排序按当前表格最右侧日期的值计算。绿色表示相比前一列增加，红色表示减少；金额变化只按 OKX 价格估算。
                  </div>
                </td>
              </tr>
            ) : null}
            {!data?.tokens?.length ? (
              <tr>
                <td colSpan={(data?.dates.length || 0) + 1}>
                  <div className="empty">暂无代币持仓快照</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
