"use client";

import { useEffect, useMemo, useState } from "react";

import { ChainBadge, ChainFilter, formatTokenAmount, formatUsd } from "@/components/onchain-shared";
import { LoadingPanel } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { getOnchainTokenMatrix } from "@/lib/direct-data";
import type { OnchainTokenMatrixData } from "@/lib/types";

type Metric = "holders" | "balance" | "value";

export default function OnchainTokensPage() {
  const { loading, supabase } = useAuth();
  const [data, setData] = useState<OnchainTokenMatrixData | null>(null);
  const [metric, setMetric] = useState<Metric>("holders");
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

  if (loading) return <LoadingPanel />;

  function valueFor(cell: OnchainTokenMatrixData["cells"][number] | undefined) {
    if (!cell) return "-";
    if (metric === "holders") return String(cell.holderCount);
    if (metric === "balance") return formatTokenAmount(cell.balanceSum);
    return formatUsd(cell.valueUsdSum);
  }

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>按代币</h1>
          <p className="muted">Token 为行、日期为列，按持有人数、持有数量或金额观察变化。</p>
        </div>
      </div>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}

      <section className="panel">
        <div className="filter-row">
          <button className={metric === "holders" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMetric("holders")}>
            持有人数
          </button>
          <button className={metric === "balance" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMetric("balance")}>
            数量
          </button>
          <button className={metric === "value" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMetric("value")}>
            金额
          </button>
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
            {(data?.tokens || []).map((token) => (
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
                  const delta =
                    metric === "holders"
                      ? cell?.holderCountDelta
                      : metric === "balance"
                        ? cell?.balanceDelta
                        : cell?.valueUsdDelta;
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
                  <div className="empty">绿色表示相比前一列增加，红色表示减少；金额变化只按 OKX 价格估算。</div>
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
