"use client";

import { useEffect, useState } from "react";

import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { listEntities } from "@/lib/direct-data";
import type { EntityListItem } from "@/lib/types";

export default function StocksPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [stocks, setStocks] = useState<EntityListItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!profile) {
        setStocks([]);
        return;
      }
      const nextStocks = await listEntities(supabase, "stock");
      if (!cancelled) setStocks(nextStocks);
    }
    load().catch(console.error);
    return () => {
      cancelled = true;
    };
  }, [profile, supabase]);

  if (loading) return <LoadingPanel />;
  if (!profile) return <LoginRequired onLogin={signIn} />;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>股票</h1>
          <p className="muted">按你的订阅账号过滤后的股票观点。</p>
        </div>
      </div>
      <section className="table-panel">
        <table>
          <thead>
            <tr>
              <th>股票</th>
              <th>最近日期</th>
              <th>提及</th>
              <th>账号</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((item) => (
              <tr key={item.key}>
                <td>
                  <strong>{item.displayName}</strong>
                </td>
                <td>{item.latestDate || "-"}</td>
                <td>{item.mentionCount}</td>
                <td>{item.authorCount}</td>
              </tr>
            ))}
            {!stocks.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无股票观点</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
