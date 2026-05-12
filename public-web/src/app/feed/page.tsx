"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";

import { AuthorDayCard } from "@/components/author-day-card";
import { EmptyState } from "@/components/empty-state";
import { InsightListCard } from "@/components/insight-list-card";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { getVisibleAuthorTimeline, listVisibleAuthors } from "@/lib/direct-data";
import type { AuthorDetailData, AuthorListItem } from "@/lib/types";

function parsePage(value: string | null) {
  const parsed = Number.parseInt(value || "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function TimelineUpdatingNotice() {
  return (
    <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper-strong)]/70 px-4 py-3 text-sm font-medium text-[color:var(--muted-ink)]">
      正在更新右侧时间线
    </div>
  );
}

function FeedPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase } = useAuth();
  const queryParam = searchParams.get("q") || "";
  const [authors, setAuthors] = useState<AuthorListItem[]>([]);
  const [detail, setDetail] = useState<AuthorDetailData | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [showStocks, setShowStocks] = useState(true);
  const [showThemes, setShowThemes] = useState(false);
  const [showMacro, setShowMacro] = useState(false);
  const [showOther, setShowOther] = useState(false);
  const page = parsePage(searchParams.get("page"));
  const requestedId = searchParams.get("account");
  const activeId = useMemo(() => {
    if (requestedId && authors.some((item) => item.accountId === requestedId)) return requestedId;
    return authors[0]?.accountId || "";
  }, [authors, requestedId]);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setListLoading(true);
    });
    listVisibleAuthors(supabase, profile, queryParam)
      .then((rows) => {
        if (cancelled) return;
        setAuthors(rows);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "作者列表加载失败");
        setAuthors([]);
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loading, profile, queryParam, supabase]);

  useEffect(() => {
    if (loading || !activeId) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled && !loading) setDetail(null);
      });
      return () => {
        cancelled = true;
      };
    }
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setDetailLoading(true);
    });
    getVisibleAuthorTimeline(supabase, profile, activeId, page)
      .then((nextDetail) => {
        if (cancelled) return;
        setDetail(nextDetail);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "作者时间线加载失败");
        setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, loading, page, profile, supabase]);

  function selectAuthor(accountId: string) {
    if (accountId === activeId) return;
    const next = new URLSearchParams(searchParams);
    next.set("account", accountId);
    next.delete("page");
    router.push(`/feed?${next.toString()}`, { scroll: false });
    setPanelOpen(false);
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const nextQuery = String(formData.get("q") || "").trim();
    const next = new URLSearchParams(searchParams);
    if (nextQuery) next.set("q", nextQuery);
    else next.delete("q");
    next.delete("account");
    next.delete("page");
    router.push(next.toString() ? `/feed?${next.toString()}` : "/feed", { scroll: false });
  }

  if (loading) return <LoadingPanel />;

  return (
    <main className="page space-y-6 lg:flex lg:h-[calc(100vh-40px)] lg:flex-col lg:overflow-hidden lg:pb-0">
      <Card className="lg:shrink-0">
        <CardHeader className="lg:py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">{profile ? "我的订阅" : "公开预览"}</Badge>
            {!profile ? <Badge variant="neutral">仅 1 条</Badge> : null}
          </div>
          <CardTitle className="text-3xl">按人看观点时间线</CardTitle>
          <CardDescription>
            左侧快速切换订阅账号，右侧查看该账号按日沉淀的观点、逻辑、证据和来源。
          </CardDescription>
        </CardHeader>
      </Card>

      {!profile ? <SignInCta onLogin={signIn} compact /> : null}

      <div className="lg:hidden">
        <Button type="button" variant="secondary" onClick={() => setPanelOpen((current) => !current)}>
          {panelOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          {panelOpen ? "收起切换列表" : "展开切换列表"}
        </Button>
      </div>

      <div className="grid gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[336px_minmax(0,1fr)]">
        <aside className={panelOpen ? "block lg:min-h-0" : "hidden lg:block lg:min-h-0"}>
          <Card className="h-full overflow-hidden lg:flex lg:flex-col">
            <CardHeader className="shrink-0 space-y-4 border-b border-[color:var(--border)] bg-[color:var(--paper-strong)]/60">
              <div>
                <CardTitle className="text-xl">快速切换</CardTitle>
                <CardDescription>{profile ? "你的订阅账号" : "公开轻量预览"}</CardDescription>
              </div>
              <form className="space-y-3" onSubmit={search}>
                <Input key={queryParam} name="q" defaultValue={queryParam} placeholder="搜索账号" />
                <Button type="submit" className="w-full">
                  <Search className="h-4 w-4" />
                  更新列表
                </Button>
              </form>
            </CardHeader>
            <CardContent className="min-h-0 space-y-3 overflow-y-auto overscroll-contain p-4 lg:flex-1">
              {listLoading ? <div className="empty">列表加载中</div> : null}
              {!listLoading && authors.map((author) => (
                <InsightListCard
                  key={author.accountId}
                  type="author"
                  item={author}
                  active={author.accountId === activeId}
                  onSelect={() => selectAuthor(author.accountId)}
                />
              ))}
              {!listLoading && authors.length === 0 ? (
                <div className="empty">{profile ? "暂无订阅数据" : "暂无公开预览数据"}</div>
              ) : null}
            </CardContent>
          </Card>
        </aside>

        <section className="min-w-0 space-y-4 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain lg:pr-1">
          {error ? <div className="empty field-error">{error}</div> : null}
          {detailLoading ? <TimelineUpdatingNotice /> : null}
          {detail ? (
            <>
              <Card>
                <CardHeader className="gap-4 sm:flex sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <CardTitle className="text-3xl">{detail.accountName || detail.authorNickname}</CardTitle>
                    <CardDescription className="break-all">{detail.profileUrl}</CardDescription>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-3 sm:justify-end">
                    <label className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--muted-ink)]">
                      <input
                        type="checkbox"
                        checked={showStocks}
                        onChange={(event) => setShowStocks(event.target.checked)}
                        className="feed-filter-checkbox"
                      />
                      股票
                    </label>
                    <label className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--muted-ink)]">
                      <input
                        type="checkbox"
                        checked={showThemes}
                        onChange={(event) => setShowThemes(event.target.checked)}
                        className="feed-filter-checkbox"
                      />
                      Theme
                    </label>
                    <label className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--muted-ink)]">
                      <input
                        type="checkbox"
                        checked={showMacro}
                        onChange={(event) => setShowMacro(event.target.checked)}
                        className="feed-filter-checkbox"
                      />
                      宏观
                    </label>
                    <label className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--muted-ink)]">
                      <input
                        type="checkbox"
                        checked={showOther}
                        onChange={(event) => setShowOther(event.target.checked)}
                        className="feed-filter-checkbox"
                      />
                      其他
                    </label>
                  </div>
                </CardHeader>
              </Card>
              {detail.timeline.rows.length ? (
                <div className="space-y-4">
                  {detail.timeline.rows.map((day) => (
                    <AuthorDayCard
                      key={`${detail.accountId}-${day.date}`}
                      day={day}
                      showStocks={showStocks}
                      showThemes={showThemes}
                      showMacro={showMacro}
                      showOther={showOther}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState title="这个账号还没有有效观点记录" description="完成抓取和分析后，这里会出现观点时间线。" />
              )}
            </>
          ) : null}
          {!profile && detail ? <SignInCta onLogin={signIn} /> : null}
        </section>
      </div>
    </main>
  );
}

export default function FeedPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <FeedPageContent />
    </Suspense>
  );
}
