"use client";

import { useEffect, useState } from "react";

import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { listFeed } from "@/lib/direct-data";
import type { FeedDay } from "@/lib/types";

export default function FeedPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [feed, setFeed] = useState<FeedDay[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!profile) {
        setFeed([]);
        return;
      }
      const nextFeed = await listFeed(supabase, profile, 60);
      if (!cancelled) setFeed(nextFeed);
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
          <h1>我的订阅</h1>
          <p className="muted">这里只显示你已订阅 X 账号的观点时间线。</p>
        </div>
      </div>
      <section className="feed-list">
        {feed.map((item) => (
          <article className="feed-item" key={item.id}>
            <div className="feed-meta">
              <a href={item.profileUrl} target="_blank" rel="noreferrer">
                @{item.username}
              </a>
              <span>{item.date}</span>
              <span>{item.noteCount} 条内容</span>
            </div>
            <h2>{item.displayName}</h2>
            <p>{item.summary}</p>
            {item.viewpoints.length ? (
              <div className="viewpoint-list">
                {item.viewpoints.slice(0, 8).map((viewpoint, index) => (
                  <span className="status-pill" key={`${item.id}-${index}`}>
                    {String(viewpoint.entity_name || viewpoint.entityKey || "观点")}
                  </span>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {!feed.length ? <div className="empty">暂无订阅数据</div> : null}
      </section>
    </main>
  );
}
