"use client";

import Link from "next/link";
import { ArrowRight, Library, Radio, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { SignInCta } from "@/components/signin-cta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader, StatCard, StatGrid } from "@/components/ui/page";
import { useAuth } from "@/lib/auth-context";
import { getHomeStats, listFeed as listDirectFeed } from "@/lib/direct-data";
import type { Domain, FeedDay, HomeStats } from "@/lib/types";

export function HomePageContent({ domain = "stock" }: { domain?: Domain }) {
  const { loading, profile, signIn, supabase, authAvailable } = useAuth();
  const [stats, setStats] = useState<HomeStats>({ approvedCount: 0, subscribedCount: 0 });
  const [feed, setFeed] = useState<FeedDay[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;

    async function load() {
      const [nextStats, nextFeed] = await Promise.all([
        getHomeStats(supabase, domain),
        listDirectFeed(supabase, profile, 6, domain),
      ]);
      if (!cancelled) {
        setStats(nextStats);
        setFeed(nextFeed);
        setError(null);
      }
    }

    load().catch((err) => {
      if (cancelled) return;
      setStats({ approvedCount: 0, subscribedCount: 0 });
      setFeed([]);
      setError(err instanceof Error ? err.message : "数据加载失败");
    });

    return () => {
      cancelled = true;
    };
  }, [domain, loading, profile, supabase]);

  const isCrypto = domain === "crypto";
  const basePath = isCrypto ? "/crypto" : "";
  const title = isCrypto ? "加密信号浏览" : "股票观点浏览";
  const description = isCrypto
    ? "把已审批 X 账号里的加密项目、资产与信号重新整理成可浏览的时间线、矩阵和详情页。"
    : "把已审批 X 账号里的股票观点整理成可浏览的时间线、矩阵、叙事简报与风险快照。";

  return (
    <main className="page">
      <PageHeader
        eyebrow="Jibai Public"
        title={title}
        description={description}
        badges={
          <>
            <Badge variant="warm">{isCrypto ? "加密" : "股票"}</Badge>
            <Badge variant="neutral">{profile ? "完整模式" : "公开预览"}</Badge>
          </>
        }
        actions={
          <>
            <Button asChild>
              <Link href={`${basePath}/accounts`}>
                <Library className="h-4 w-4" />
                账号库
              </Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href={`${basePath}/feed`}>
                <ArrowRight className="h-4 w-4" />
                {profile ? "我的订阅" : "查看预览"}
              </Link>
            </Button>
          </>
        }
      />

      {!profile ? <SignInCta onLogin={signIn} compact authAvailable={authAvailable} /> : null}

      <StatGrid>
        <StatCard
          label="已审批账号"
          value={stats.approvedCount}
          hint="账号库对游客开放，登录后按你的订阅生成个性化视图。"
          icon={<Radio className="h-4 w-4" />}
        />
        <StatCard
          label="我的订阅"
          value={stats.subscribedCount}
          hint={profile ? "会直接影响你的时间线、矩阵和详情页内容。" : "登录后可开始建立自己的订阅列表。"}
          icon={<Library className="h-4 w-4" />}
        />
        <StatCard
          label="当前身份"
          value={profile?.isAdmin ? "Admin" : profile ? "User" : "Guest"}
          hint="管理员可查看额外的审批、抓取与运行状态页面。"
          icon={<ShieldCheck className="h-4 w-4" />}
        />
      </StatGrid>

      <div className="hero-grid">
        <Card variant="elevated">
          <CardHeader className="gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="neutral">快速开始</Badge>
              <Badge variant="warm">账号库 / 时间线 / 详情页</Badge>
            </div>
            <CardTitle className="text-3xl sm:text-4xl">从公开账号快速进入观点与信号</CardTitle>
            <CardDescription className="text-[15px] leading-7">
              先浏览账号库，再按作者、时间线和标的逐层查看内容。公开预览适合快速了解，登录后可以围绕自己的订阅继续深入。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[24px] border border-[color:var(--border)] bg-white/70 p-4">
                <p className="text-sm font-semibold text-[color:var(--ink)]">账号库</p>
                <p className="mt-2 text-sm leading-6 text-[color:var(--muted-ink)]">查看已审批账号，挑选值得持续跟踪的作者。</p>
              </div>
              <div className="rounded-[24px] border border-[color:var(--border)] bg-white/70 p-4">
                <p className="text-sm font-semibold text-[color:var(--ink)]">时间线与详情</p>
                <p className="mt-2 text-sm leading-6 text-[color:var(--muted-ink)]">按作者和标的回看观点、信号、矩阵与最近更新。</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="gap-4">
            <div>
              <CardTitle>{profile ? "最近更新" : "公开预览"}</CardTitle>
              <CardDescription>
                {profile ? "来自你的订阅账号。" : "未登录时只展示 1 个真实对象的少量内容。"}
              </CardDescription>
            </div>
            <Button asChild variant="secondary">
              <Link href={`${basePath}/feed`}>进入时间线</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
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
                    <p className="muted">{isCrypto ? `${item.viewpointCount} 个标的信号` : item.summary}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty">{profile ? "暂无订阅更新" : "暂无公开预览数据"}</div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
