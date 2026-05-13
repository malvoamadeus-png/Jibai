"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
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

function buildFeedUrl(query: string, accountId: string, page: number) {
  const next = new URLSearchParams();
  if (query) next.set("q", query);
  if (accountId) next.set("account", accountId);
  if (page > 1) next.set("page", String(page));
  const params = next.toString();
  return params ? `/feed?${params}` : "/feed";
}

function FeedPageContent() {
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase } = useAuth();
  const [listQuery, setListQuery] = useState(searchParams.get("q") || "");
  const [selectedAccountId, setSelectedAccountId] = useState(searchParams.get("account") || "");
  const [page, setPage] = useState(() => parsePage(searchParams.get("page")));
  const [authors, setAuthors] = useState<AuthorListItem[]>([]);
  const [detail, setDetail] = useState<AuthorDetailData | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const activeId = selectedAccountId || authors[0]?.accountId || "";

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setListLoading(true);
    });
    listVisibleAuthors(supabase, profile, listQuery)
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
  }, [loading, profile, listQuery, supabase]);

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

  useEffect(() => {
    function syncFromLocation() {
      const next = new URLSearchParams(window.location.search);
      setListQuery(next.get("q") || "");
      setSelectedAccountId(next.get("account") || "");
      setPage(parsePage(next.get("page")));
    }

    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, []);

  function selectAuthor(accountId: string) {
    setSelectedAccountId(accountId);
    setPage(1);
    window.history.pushState(null, "", buildFeedUrl(listQuery, accountId, 1));
    setPanelOpen(false);
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const nextQuery = String(formData.get("q") || "").trim();
    setListQuery(nextQuery);
    setSelectedAccountId("");
    setPage(1);
    window.history.pushState(null, "", buildFeedUrl(nextQuery, "", 1));
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
            左侧快速切换订阅账号，右侧查看该账号按日沉淀的股票观点、逻辑、证据和来源。
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
                <Input key={listQuery} name="q" defaultValue={listQuery} placeholder="搜索账号" />
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
                </CardHeader>
              </Card>
              {detail.timeline.rows.length ? (
                <div className="space-y-4">
                  {detail.timeline.rows.map((day) => (
                    <AuthorDayCard
                      key={`${detail.accountId}-${day.date}`}
                      day={day}
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
