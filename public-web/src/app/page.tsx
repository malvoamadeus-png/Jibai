"use client";

import Link from "next/link";
import { ArrowRight, Library, Radio, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { SignInCta } from "@/components/signin-cta";
import { useAuth } from "@/lib/auth-context";
import { listAccounts as listDirectAccounts, listFeed as listDirectFeed } from "@/lib/direct-data";
import type { AccountListItem, FeedDay } from "@/lib/types";

export default function HomePage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [accounts, setAccounts] = useState<AccountListItem[]>([]);
  const [feed, setFeed] = useState<FeedDay[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    async function load() {
      const [nextAccounts, nextFeed] = await Promise.all([
        listDirectAccounts(supabase, profile),
        listDirectFeed(supabase, profile, 6),
      ]);
      if (!cancelled) {
        setAccounts(nextAccounts);
        setFeed(nextFeed);
        setError(null);
      }
    }
    load().catch((err) => {
      if (cancelled) return;
      setAccounts([]);
      setFeed([]);
      setError(err instanceof Error ? err.message : "数据加载失败");
    });
    return () => {
      cancelled = true;
    };
  }, [loading, profile, supabase]);

  return (
    <main className="page">
      <section className="hero-grid">
        <div className="panel">
          <h1 className="brand-title">集百</h1>
          <p className="muted">
            把已审批 X 账号的观点按人、股票和 Theme 重新整理。未登录可看账号库和一条轻量预览，登录后按你的订阅范围展开完整时间线。
          </p>
          <div className="submit-row">
            <Link className="primary-button" href="/accounts">
              <Library size={16} />
              账号库
            </Link>
            <Link className="secondary-button" href="/feed">
              <ArrowRight size={16} />
              {profile ? "我的订阅" : "看一条预览"}
            </Link>
          </div>
          {!profile ? <SignInCta onLogin={signIn} compact /> : null}
          <div className="metric-row">
            <div className="metric">
              <Radio size={18} />
              <strong>{accounts.length}</strong>
              <span className="muted">已审批账号</span>
            </div>
            <div className="metric">
              <Library size={18} />
              <strong>{accounts.filter((item) => item.subscribed).length}</strong>
              <span className="muted">我的订阅</span>
            </div>
            <div className="metric">
              <ShieldCheck size={18} />
              <strong>{profile?.isAdmin ? "Admin" : profile ? "User" : "游客"}</strong>
              <span className="muted">当前身份</span>
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="section-head">
            <div>
              <h2>{profile ? "最近更新" : "公开预览"}</h2>
              <p className="muted">{profile ? "来自你的订阅账号。" : "未登录只展示 1 个真实对象的少量内容。"}</p>
            </div>
            <Link className="secondary-button" href="/feed">
              进入时间线
            </Link>
          </div>
          {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}
          {feed.length ? (
            <div className="feed-list">
              {feed.slice(0, 3).map((item) => (
                <article className="feed-item" key={item.id}>
                  <div className="feed-meta">
                    <span>@{item.username}</span>
                    <span>{item.date}</span>
                    <span>{item.noteCount} 条内容</span>
                  </div>
                  <h3>{item.displayName || item.username}</h3>
                  <p className="muted">{item.summary}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty">{profile ? "暂无订阅更新" : "暂无公开预览数据"}</div>
          )}
        </div>
      </section>
    </main>
  );
}
