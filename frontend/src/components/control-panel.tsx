"use client";

import type { ReactNode } from "react";
import { useEffect, useState, useTransition } from "react";
import {
  ChevronDown,
  Clock3,
  Database,
  Play,
  Plus,
  RefreshCcw,
  Save,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type {
  AiSettings,
  ControlAccountConfig,
  ControlAccountStatus,
  ControlPanelData,
  ControlSavePayload,
  ManualRunTarget,
  XSettings,
  XiaohongshuSettings,
} from "@/lib/types";
import { cn, formatCount, stripTime } from "@/lib/utils";

const DEFAULT_ACCOUNT_FETCH_LIMIT = 5;

function SectionField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
      <div className="space-y-1">
        <p className="text-sm font-medium text-[color:var(--ink)]">{label}</p>
        {hint ? <p className="text-xs leading-5 text-[color:var(--muted-ink)]">{hint}</p> : null}
      </div>
      {children}
    </div>
  );
}

function CheckboxField({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (nextValue: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
      <div className="space-y-1">
        <p className="text-sm font-medium text-[color:var(--ink)]">{label}</p>
        {hint ? <p className="text-xs leading-5 text-[color:var(--muted-ink)]">{hint}</p> : null}
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-5 w-5 rounded border-[color:var(--border-strong)] accent-[color:var(--accent)]"
      />
    </label>
  );
}

function StatusPill({
  tone,
  children,
}: {
  tone: "neutral" | "positive" | "danger" | "warm";
  children: ReactNode;
}) {
  return <Badge variant={tone}>{children}</Badge>;
}

function accountStatusTone(status: ControlAccountStatus["lastStatus"]) {
  if (status === "success") return "positive" as const;
  if (status === "failed") return "danger" as const;
  return "neutral" as const;
}

function accountStatusLabel(status: ControlAccountStatus["lastStatus"]) {
  if (status === "success") return "最近成功";
  if (status === "failed") return "最近异常";
  return "尚未运行";
}

function manualRunTone(status: ControlPanelData["runtime"]["manualRun"]["status"]) {
  if (status === "succeeded") return "positive" as const;
  if (status === "failed") return "danger" as const;
  if (status === "running") return "warm" as const;
  return "neutral" as const;
}

function manualRunLabel(status: ControlPanelData["runtime"]["manualRun"]["status"]) {
  if (status === "succeeded") return "最近手动运行成功";
  if (status === "failed") return "最近手动运行失败";
  if (status === "running") return "手动运行中";
  return "未手动运行";
}

function AccountEditor({
  title,
  hint,
  accounts,
  maxLimit,
  profilePlaceholder,
  onChange,
}: {
  title: string;
  hint: string;
  accounts: ControlAccountConfig[];
  maxLimit: number;
  profilePlaceholder: string;
  onChange: (nextAccounts: ControlAccountConfig[]) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[color:var(--ink)]">{title}</p>
          <p className="mt-1 text-xs leading-5 text-[color:var(--muted-ink)]">{hint}</p>
          <p className="mt-1 text-xs leading-5 text-[color:var(--soft-ink)]">
            最后一列是每次抓取的最近条数。
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() =>
            onChange([
              ...accounts,
              {
                name: "",
                profileUrl: "",
                limit: Math.min(DEFAULT_ACCOUNT_FETCH_LIMIT, maxLimit),
              },
            ])
          }
        >
          <Plus className="h-3.5 w-3.5" />
          新增账号
        </Button>
      </div>

      <div className="space-y-3">
        {accounts.map((account, index) => (
          <div
            key={`${title}-${index}`}
            className="grid gap-3 rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4 md:grid-cols-[180px_1fr_120px_52px]"
          >
            <Input
              value={account.name}
              placeholder="展示名称"
              onChange={(event) =>
                onChange(
                  accounts.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, name: event.target.value } : item,
                  ),
                )
              }
            />
            <Input
              value={account.profileUrl}
              placeholder={profilePlaceholder}
              onChange={(event) =>
                onChange(
                  accounts.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, profileUrl: event.target.value } : item,
                  ),
                )
              }
            />
            <Input
              type="number"
              min={1}
              max={maxLimit}
              placeholder={String(Math.min(DEFAULT_ACCOUNT_FETCH_LIMIT, maxLimit))}
              title={`每次抓取最近 ${maxLimit} 条以内`}
              value={String(account.limit)}
              onChange={(event) =>
                onChange(
                  accounts.map((item, itemIndex) =>
                    itemIndex === index
                      ? {
                          ...item,
                          limit: Number.parseInt(event.target.value || "1", 10) || 1,
                        }
                      : item,
                  ),
                )
              }
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange(accounts.filter((_, itemIndex) => itemIndex !== index))}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}

        {accounts.length === 0 ? (
          <div className="rounded-[24px] border border-dashed border-[color:var(--border-strong)] px-4 py-5 text-sm text-[color:var(--muted-ink)]">
            还没有配置账号。
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AccountStatusList({
  title,
  statuses,
}: {
  title: string;
  statuses: ControlAccountStatus[];
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-medium text-[color:var(--ink)]">{title}</p>
        <p className="mt-1 text-xs leading-5 text-[color:var(--muted-ink)]">
          页面只展示高层状态，不再显示底层代码错误。
        </p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {statuses.map((item) => (
          <div
            key={item.name}
            className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--paper)] p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-base font-medium text-[color:var(--ink)]">{item.name}</p>
                <p className="mt-1 text-xs text-[color:var(--soft-ink)]">{stripTime(item.lastRunAt)}</p>
              </div>
              <StatusPill tone={accountStatusTone(item.lastStatus)}>
                {accountStatusLabel(item.lastStatus)}
              </StatusPill>
            </div>
            <div className="mt-4 grid gap-3 text-sm text-[color:var(--muted-ink)] sm:grid-cols-3">
              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">候选数</p>
                <p className="mt-1 font-medium text-[color:var(--ink)]">
                  {item.candidateCount === null ? "-" : formatCount(item.candidateCount)}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">新增数</p>
                <p className="mt-1 font-medium text-[color:var(--ink)]">
                  {item.newNoteCount === null ? "-" : formatCount(item.newNoteCount)}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">已见帖子</p>
                <p className="mt-1 font-medium text-[color:var(--ink)]">{formatCount(item.seenCount)}</p>
              </div>
            </div>
            {item.lastError ? (
              <div className="mt-4 rounded-[20px] border border-[color:rgba(138,61,61,0.2)] bg-[color:rgba(138,61,61,0.08)] px-3 py-3 text-xs leading-5 text-[#7d2a2a]">
                {item.lastError}
              </div>
            ) : null}
          </div>
        ))}

        {statuses.length === 0 ? (
          <div className="rounded-[24px] border border-dashed border-[color:var(--border-strong)] px-4 py-5 text-sm text-[color:var(--muted-ink)]">
            还没有账号状态记录。
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AdvancedSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <details className="group rounded-[28px] border border-[color:var(--border)] bg-[color:var(--paper)]/70 p-4">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-sm font-medium text-[color:var(--ink)]">{title}</p>
          <p className="text-xs leading-5 text-[color:var(--muted-ink)]">{description}</p>
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--soft-ink)] transition group-open:rotate-180" />
      </summary>

      <div className="mt-4 space-y-4 border-t border-[color:var(--border)] pt-4">{children}</div>
    </details>
  );
}

function ScheduleTimeEditor({
  title,
  hint,
  times,
  defaultTime,
  onChange,
}: {
  title: string;
  hint: string;
  times: string[];
  defaultTime: string;
  onChange: (nextTimes: string[]) => void;
}) {
  return (
    <div className="space-y-3 rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-sm font-medium text-[color:var(--ink)]">{title}</p>
          <p className="text-xs leading-5 text-[color:var(--muted-ink)]">{hint}</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onChange([...times, defaultTime])}
        >
          <Plus className="h-3.5 w-3.5" />
          新增时间
        </Button>
      </div>
      <div className="space-y-3">
        {times.map((item, index) => (
          <div
            key={`${title}-${index}`}
            className="grid gap-3 rounded-[20px] border border-[color:var(--border)] bg-[color:var(--paper)] p-3 md:grid-cols-[1fr_52px]"
          >
            <Input
              value={item}
              placeholder={defaultTime}
              onChange={(event) =>
                onChange(
                  times.map((time, timeIndex) =>
                    timeIndex === index ? event.target.value : time,
                  ),
                )
              }
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={times.length === 1}
              onClick={() => onChange(times.filter((_, timeIndex) => timeIndex !== index))}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatModelList(values: string[]) {
  return values.join(", ");
}

function parseModelListInput(value: string) {
  const deduped: string[] = [];
  for (const item of value.split(/[,\n]/)) {
    const trimmed = item.trim();
    if (trimmed && !deduped.includes(trimmed)) {
      deduped.push(trimmed);
    }
  }
  return deduped;
}

export function ControlPanel({ initialData }: { initialData: ControlPanelData }) {
  const [data, setData] = useState(initialData);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function fetchControlState() {
    const response = await fetch("/api/local/control", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.message || "刷新状态失败");
    }
    setData(payload as ControlPanelData);
    setApiKeyInput("");
    setClearApiKey(false);
  }

  useEffect(() => {
    if (data.runtime.manualRun.status !== "running") {
      return;
    }
    const timer = window.setInterval(() => {
      void fetchControlState().catch((error) => {
        setErrorText(error instanceof Error ? error.message : "刷新状态失败");
      });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [data.runtime.manualRun.status]);

  function setScheduleTimes(platform: "xiaohongshu" | "x", nextScheduleTimes: string[]) {
    setData((current) => ({
      ...current,
      runtime: {
        ...current.runtime,
        ...(platform === "xiaohongshu"
          ? { xiaohongshuScheduleTimes: nextScheduleTimes }
          : { xScheduleTimes: nextScheduleTimes }),
      },
    }));
  }

  function setXhsConfig(updater: (current: XiaohongshuSettings) => XiaohongshuSettings) {
    setData((current) => ({
      ...current,
      xiaohongshu: {
        ...current.xiaohongshu,
        config: updater(current.xiaohongshu.config),
      },
    }));
  }

  function setXConfig(updater: (current: XSettings) => XSettings) {
    setData((current) => ({
      ...current,
      x: {
        ...current.x,
        config: updater(current.x.config),
      },
    }));
  }

  function setAiConfig(updater: (current: AiSettings) => AiSettings) {
    setData((current) => ({
      ...current,
      ai: {
        ...current.ai,
        config: updater(current.ai.config),
      },
    }));
  }

  function saveSettings() {
    setFeedback(null);
    setErrorText(null);
    setBusyAction("save");
    startTransition(() => {
      void (async () => {
        try {
          const payload: ControlSavePayload = {
            xiaohongshuScheduleTimes: data.runtime.xiaohongshuScheduleTimes,
            xScheduleTimes: data.runtime.xScheduleTimes,
            xiaohongshu: data.xiaohongshu.config,
            x: data.x.config,
            ai: {
              provider: data.ai.config.provider,
              model: data.ai.config.model,
              fallbackModels: data.ai.config.fallbackModels,
              reasoningEffort: data.ai.config.reasoningEffort,
              baseUrl: data.ai.config.baseUrl,
              apiKey: apiKeyInput,
              clearApiKey,
            },
          };
          const response = await fetch("/api/local/control", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const body = await response.json();
          if (!response.ok) {
            const issues = Array.isArray(body.issues)
              ? body.issues
                  .map((item: { message?: string }) => item.message)
                  .filter(Boolean)
                  .join("；")
              : "";
            throw new Error(issues || body.message || "保存配置失败");
          }
          setData(body as ControlPanelData);
          setApiKeyInput("");
          setClearApiKey(false);
          setFeedback("配置已保存");
        } catch (error) {
          setErrorText(error instanceof Error ? error.message : "保存配置失败");
        } finally {
          setBusyAction(null);
        }
      })();
    });
  }

  function refreshNow() {
    setFeedback(null);
    setErrorText(null);
    setBusyAction("refresh");
    startTransition(() => {
      void fetchControlState()
        .then(() => setFeedback("状态已刷新"))
        .catch((error) => {
          setErrorText(error instanceof Error ? error.message : "刷新状态失败");
        })
        .finally(() => {
          setBusyAction(null);
        });
    });
  }

  function triggerRun(target: ManualRunTarget) {
    setFeedback(null);
    setErrorText(null);
    setBusyAction(`run-${target}`);
    startTransition(() => {
      void (async () => {
        try {
          const response = await fetch("/api/local/control/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target }),
          });
          const body = await response.json();
          if (!response.ok && !body.data) {
            throw new Error(body.message || "触发运行失败");
          }
          setData(body.data as ControlPanelData);
          setFeedback(body.accepted ? "已开始执行手动运行" : "已有任务在运行，已刷新当前状态");
        } catch (error) {
          setErrorText(error instanceof Error ? error.message : "触发运行失败");
        } finally {
          setBusyAction(null);
        }
      })();
    });
  }

  const actionBusy = isPending || data.runtime.manualRun.status === "running";
  const xhsLoginReady = data.xiaohongshu.status.loginStatus === "ready";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <StatusPill tone={manualRunTone(data.runtime.manualRun.status)}>
              {manualRunLabel(data.runtime.manualRun.status)}
            </StatusPill>
            <div className="space-y-2">
              <CardTitle className="text-3xl">配置与运行台</CardTitle>
              <CardDescription>
                同一个本地网页里完成平台启用、账号管理、调度时间、手动运行和最近运行状态查看。
              </CardDescription>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" onClick={refreshNow} disabled={isPending}>
              <RefreshCcw className="h-4 w-4" />
              刷新状态
            </Button>
            <Button type="button" onClick={saveSettings} disabled={actionBusy || busyAction === "save"}>
              <Save className="h-4 w-4" />
              保存配置
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {feedback ? (
            <div className="rounded-[22px] border border-[color:rgba(65,122,90,0.24)] bg-[color:rgba(65,122,90,0.08)] px-4 py-3 text-sm text-[#28593f]">
              {feedback}
            </div>
          ) : null}
          {errorText ? (
            <div className="rounded-[22px] border border-[color:rgba(138,61,61,0.24)] bg-[color:rgba(138,61,61,0.08)] px-4 py-3 text-sm text-[#7d2a2a]">
              {errorText}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
              <div className="flex items-center gap-2 text-[color:var(--accent-strong)]">
                <Clock3 className="h-4 w-4" />
                <span className="text-xs uppercase tracking-[0.18em]">最近运行</span>
              </div>
              <p className="mt-3 text-lg font-semibold text-[color:var(--ink)]">{stripTime(data.runtime.lastRunAt)}</p>
            </div>
            <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
              <div className="flex items-center gap-2 text-[color:var(--accent-strong)]">
                <Database className="h-4 w-4" />
                <span className="text-xs uppercase tracking-[0.18em]">SQLite</span>
              </div>
              <p className="mt-3 text-sm font-medium text-[color:var(--ink)]">{data.runtime.dbPath}</p>
              <p className="mt-2 text-xs text-[color:var(--muted-ink)]">
                {data.runtime.dbPresent ? "数据库已就绪" : "数据库文件尚未生成"}
              </p>
            </div>
            <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
              <div className="flex items-center gap-2 text-[color:var(--accent-strong)]">
                {xhsLoginReady ? <ShieldCheck className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
                <span className="text-xs uppercase tracking-[0.18em]">小红书登录</span>
              </div>
              <p className="mt-3 text-lg font-semibold text-[color:var(--ink)]">
                {xhsLoginReady ? "已检测到会话" : "未检测到会话"}
              </p>
              <p className="mt-2 text-xs text-[color:var(--muted-ink)]">{data.xiaohongshu.status.loginPath}</p>
            </div>
            <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4">
              <div className="flex items-center gap-2 text-[color:var(--accent-strong)]">
                <SlidersHorizontal className="h-4 w-4" />
                <span className="text-xs uppercase tracking-[0.18em]">数据概览</span>
              </div>
              <p className="mt-3 text-sm font-medium text-[color:var(--ink)]">
                作者 {formatCount(data.stats.authorCount)} · 股票 {formatCount(data.stats.stockCount)} · Theme{" "}
                {formatCount(data.stats.themeCount)}
              </p>
              <p className="mt-2 text-xs text-[color:var(--muted-ink)]">
                内容总数 {formatCount(data.stats.contentCount)}
              </p>
            </div>
          </div>

          {data.runtime.latestError ? (
            <div className="rounded-[22px] border border-[color:rgba(138,61,61,0.22)] bg-[color:rgba(138,61,61,0.08)] px-4 py-3 text-sm text-[#7d2a2a]">
              最近一次异常：{data.runtime.latestError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>调度与手动运行</CardTitle>
            <CardDescription>
              保存后，已在终端运行中的 scheduler 需要重启一次，才会读取新的每日执行时间。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 xl:grid-cols-2">
              <ScheduleTimeEditor
                title="小红书每日执行时间"
                hint="只触发小红书抓取与分析。"
                times={data.runtime.xiaohongshuScheduleTimes}
                defaultTime="10:00"
                onChange={(nextTimes) => setScheduleTimes("xiaohongshu", nextTimes)}
              />
              <ScheduleTimeEditor
                title="X 每日执行时间"
                hint="只触发 X 抓取与分析。"
                times={data.runtime.xScheduleTimes}
                defaultTime="22:00"
                onChange={(nextTimes) => setScheduleTimes("x", nextTimes)}
              />
            </div>

            <div className="space-y-3">
              <p className="text-sm font-medium text-[color:var(--ink)]">手动立即执行</p>
              <div className="flex flex-wrap gap-3">
                <Button type="button" onClick={() => triggerRun("enabled")} disabled={actionBusy}>
                  <Play className="h-4 w-4" />
                  运行已启用平台
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => triggerRun("xiaohongshu")}
                  disabled={actionBusy}
                >
                  仅运行小红书
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => triggerRun("x")}
                  disabled={actionBusy}
                >
                  仅运行 X
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>手动运行状态</CardTitle>
            <CardDescription>这里只显示高层结果，不直接展示 stdout、stderr 或代码错误堆栈。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill tone={manualRunTone(data.runtime.manualRun.status)}>
                {manualRunLabel(data.runtime.manualRun.status)}
              </StatusPill>
              <span className="text-sm text-[color:var(--muted-ink)]">
                开始：{stripTime(data.runtime.manualRun.startedAt)}
              </span>
              <span className="text-sm text-[color:var(--muted-ink)]">
                结束：{stripTime(data.runtime.manualRun.finishedAt)}
              </span>
            </div>
            <p className="text-sm leading-6 text-[color:var(--muted-ink)]">{data.runtime.manualRun.summary}</p>

            <div className="space-y-3">
              {data.runtime.manualRun.commands.map((command, index) => (
                <div
                  key={`${command.label}-${index}`}
                  className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-[color:var(--ink)]">{command.label}</p>
                      <p className="mt-1 text-xs text-[color:var(--soft-ink)]">
                        用时 {(command.durationMs / 1000).toFixed(1)} 秒
                      </p>
                    </div>
                    <StatusPill tone={command.exitCode === 0 ? "positive" : "danger"}>
                      {command.exitCode === 0 ? "执行完成" : "执行失败"}
                    </StatusPill>
                  </div>
                </div>
              ))}

              {data.runtime.manualRun.commands.length === 0 ? (
                <div className="rounded-[24px] border border-dashed border-[color:var(--border-strong)] px-4 py-5 text-sm text-[color:var(--muted-ink)]">
                  暂时还没有手动运行记录。
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-2">
              <CardTitle>AI 配置</CardTitle>
              <CardDescription>
                支持 OpenAI-compatible 中转站和 Anthropic。API key 只会提交到服务端本地配置文件，不会回传到浏览器。
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill
                tone={
                  clearApiKey
                    ? "warm"
                    : data.ai.config.hasApiKey
                      ? "positive"
                      : "danger"
                }
              >
                {clearApiKey
                  ? "将清除当前 Key"
                  : data.ai.config.hasApiKey
                    ? "已配置 Key"
                    : "未配置 Key"}
              </StatusPill>
              <span className="text-xs text-[color:var(--muted-ink)]">
                {clearApiKey
                  ? "保存后将删除当前 API key"
                  : data.ai.config.apiKeyHint ?? "当前没有可用的 API key"}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <details className="group rounded-[28px] border border-[color:var(--border)] bg-[color:var(--paper)]/70 p-4">
            <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
              <div className="space-y-1">
                <p className="text-sm font-medium text-[color:var(--ink)]">展开 AI 配置</p>
              </div>
              <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--soft-ink)] transition group-open:rotate-180" />
            </summary>
            <div className="mt-4 space-y-4 border-t border-[color:var(--border)] pt-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <SectionField
              label="Provider"
              hint="OpenAI-compatible 适用于官方 OpenAI 与兼容中转站；Anthropic 直接走 Claude。"
            >
              <select
                value={data.ai.config.provider}
                onChange={(event) => {
                  const provider = event.target.value as AiSettings["provider"];
                  setAiConfig((current) => ({
                    ...current,
                    provider,
                    baseUrl:
                      provider === "openai-compatible" ? current.baseUrl : null,
                  }));
                }}
                className={cn(
                  "h-11 w-full rounded-[18px] border border-[color:var(--border-strong)] bg-[color:var(--paper)] px-4 text-sm text-[color:var(--ink)] outline-none transition focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color:rgba(181,106,59,0.15)]",
                )}
              >
                <option value="openai-compatible">openai-compatible</option>
                <option value="anthropic">anthropic</option>
              </select>
            </SectionField>

            <SectionField
              label="Model"
              hint={
                data.ai.config.provider === "anthropic"
                  ? "例如 claude-3-5-sonnet-latest。"
                  : "例如 gpt-5.4 或你中转站支持的模型名。"
              }
            >
              <Input
                value={data.ai.config.model}
                placeholder={
                  data.ai.config.provider === "anthropic"
                    ? "claude-3-5-sonnet-latest"
                    : "gpt-5.4"
                }
                onChange={(event) =>
                  setAiConfig((current) => ({ ...current, model: event.target.value }))
                }
              />
            </SectionField>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <SectionField
              label="Fallback Models"
              hint="多个模型用英文逗号分隔，按顺序回退。留空表示不额外回退。"
            >
              <Input
                value={formatModelList(data.ai.config.fallbackModels)}
                placeholder="gpt-4.1, gpt-4o-mini"
                onChange={(event) =>
                  setAiConfig((current) => ({
                    ...current,
                    fallbackModels: parseModelListInput(event.target.value),
                  }))
                }
              />
            </SectionField>

            <SectionField
              label="Reasoning Effort"
              hint="主要用于支持 reasoning_effort 的模型。留空则不传该参数。"
            >
              <Input
                value={data.ai.config.reasoningEffort ?? ""}
                placeholder="medium"
                onChange={(event) =>
                  setAiConfig((current) => ({
                    ...current,
                    reasoningEffort: event.target.value.trim() || null,
                  }))
                }
              />
            </SectionField>
          </div>

          {data.ai.config.provider === "openai-compatible" ? (
            <SectionField
              label="Base URL"
              hint="兼容 OpenAI API 的完整入口地址，例如官方或你的中转站地址。"
            >
              <Input
                value={data.ai.config.baseUrl ?? ""}
                placeholder="输入 Base URL"
                onChange={(event) =>
                  setAiConfig((current) => ({
                    ...current,
                    baseUrl: event.target.value.trim() || null,
                  }))
                }
              />
            </SectionField>
          ) : null}

          <SectionField
            label="API Key"
            hint="留空表示保留当前 key。勾选“清除”后，保存时会删除当前 key。"
          >
            <div className="space-y-3">
              <Input
                type="password"
                autoComplete="off"
                value={apiKeyInput}
                placeholder={
                  data.ai.config.hasApiKey ? "留空则保留当前 key" : "输入新的 API key"
                }
                onChange={(event) => {
                  setApiKeyInput(event.target.value);
                  if (event.target.value) {
                    setClearApiKey(false);
                  }
                }}
              />
              <label className="flex items-center gap-3 text-sm text-[color:var(--muted-ink)]">
                <input
                  type="checkbox"
                  checked={clearApiKey}
                  onChange={(event) => {
                    setClearApiKey(event.target.checked);
                    if (event.target.checked) {
                      setApiKeyInput("");
                    }
                  }}
                  className="h-4 w-4 rounded border-[color:var(--border-strong)] accent-[color:var(--accent)]"
                />
                保存时清除当前 API key
              </label>
            </div>
          </SectionField>
            </div>
          </details>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-2">
              <CardTitle>小红书平台配置</CardTitle>
              <CardDescription>
                管理小红书抓取开关、账号列表和当前可用状态。
              </CardDescription>
            </div>
            <StatusPill tone={xhsLoginReady ? "positive" : "danger"}>
              {xhsLoginReady ? "登录态已检测到" : "请先登录"}
            </StatusPill>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <CheckboxField
            label="启用小红书抓取"
            hint="关闭后，调度和“运行已启用平台”都会跳过小红书。"
            checked={data.xiaohongshu.config.enabled}
            onChange={(value) => setXhsConfig((current) => ({ ...current, enabled: value }))}
          />

          <AccountEditor
            title="账号列表"
            hint="请填写完整的小红书 profile_url；现在也接受不带 https:// 的输入，会自动补全。"
            accounts={data.xiaohongshu.config.accounts}
            maxLimit={20}
            profilePlaceholder="xiaohongshu.com/user/profile/..."
            onChange={(accounts) => setXhsConfig((current) => ({ ...current, accounts }))}
          />

          <AccountStatusList title="可抓取状态" statuses={data.xiaohongshu.status.accounts} />

          <AdvancedSection
            title="高级参数"
            description="Browser、Headless、抓取间隔、fallback 和旧帖过滤都放在这里，默认折叠。"
          >
            <div className="grid gap-4 xl:grid-cols-2">
              <CheckboxField
                label="排除旧帖子"
                hint="默认开启。首屏里被置顶但发布时间超过阈值的帖子会直接丢弃。"
                checked={data.xiaohongshu.config.excludeOldPosts}
                onChange={(value) =>
                  setXhsConfig((current) => ({ ...current, excludeOldPosts: value }))
                }
              />
              <CheckboxField
                label="Headless"
                hint="默认不建议开启。小红书当前以有头模式更稳。"
                checked={data.xiaohongshu.config.headless}
                onChange={(value) => setXhsConfig((current) => ({ ...current, headless: value }))}
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <SectionField label="Browser Channel" hint="默认建议 chrome。">
                <Input
                  value={data.xiaohongshu.config.browserChannel}
                  onChange={(event) =>
                    setXhsConfig((current) => ({ ...current, browserChannel: event.target.value }))
                  }
                />
              </SectionField>
              <SectionField label="旧帖阈值（天）" hint="超过这个天数的帖子会被视为置顶旧帖并跳过。">
                <Input
                  type="number"
                  min={1}
                  max={30}
                  value={String(data.xiaohongshu.config.maxPostAgeDays)}
                  onChange={(event) =>
                    setXhsConfig((current) => ({
                      ...current,
                      maxPostAgeDays: Number.parseInt(event.target.value || "5", 10) || 5,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="账号间基础间隔（秒）" hint="多账号主页访问之间的固定等待。">
                <Input
                  type="number"
                  min={0}
                  step="0.5"
                  value={String(data.xiaohongshu.config.interAccountDelaySec)}
                  onChange={(event) =>
                    setXhsConfig((current) => ({
                      ...current,
                      interAccountDelaySec: Number.parseFloat(event.target.value || "0") || 0,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="随机抖动（秒）" hint="会叠加在账号间基础间隔上，减少机械访问特征。">
                <Input
                  type="number"
                  min={0}
                  step="0.5"
                  value={String(data.xiaohongshu.config.interAccountDelayJitterSec)}
                  onChange={(event) =>
                    setXhsConfig((current) => ({
                      ...current,
                      interAccountDelayJitterSec:
                        Number.parseFloat(event.target.value || "0") || 0,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="详情抓取间隔（秒）" hint="帖子详情之间的等待时间。">
                <Input
                  type="number"
                  min={0}
                  step="0.1"
                  value={String(data.xiaohongshu.config.detailDelaySec)}
                  onChange={(event) =>
                    setXhsConfig((current) => ({
                      ...current,
                      detailDelaySec: Number.parseFloat(event.target.value || "0") || 0,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="fallback 上限" hint="每个账号每次运行最多补抓多少篇受限详情。">
                <Input
                  type="number"
                  min={0}
                  max={5}
                  value={String(data.xiaohongshu.config.detailFallbackLimitPerAccount)}
                  onChange={(event) =>
                    setXhsConfig((current) => ({
                      ...current,
                      detailFallbackLimitPerAccount:
                        Number.parseInt(event.target.value || "0", 10) || 0,
                    }))
                  }
                />
              </SectionField>
            </div>

            <CheckboxField
              label="详情 fallback"
              hint="匿名详情受限时，允许少量使用登录 cookie HTTP 回退。"
              checked={data.xiaohongshu.config.detailFallbackEnabled}
              onChange={(value) =>
                setXhsConfig((current) => ({ ...current, detailFallbackEnabled: value }))
              }
            />
          </AdvancedSection>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>X 平台配置</CardTitle>
          <CardDescription>
            管理 X 抓取开关、账号列表和当前可用状态。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <CheckboxField
            label="启用 X 抓取"
            hint="关闭后，调度和“运行已启用平台”都会跳过 X。"
            checked={data.x.config.enabled}
            onChange={(value) => setXConfig((current) => ({ ...current, enabled: value }))}
          />

          <AccountEditor
            title="账号列表"
            hint="请填写 X 用户主页链接；现在也接受不带 https:// 的输入，会自动补全。"
            accounts={data.x.config.accounts}
            maxLimit={20}
            profilePlaceholder="x.com/username"
            onChange={(accounts) => setXConfig((current) => ({ ...current, accounts }))}
          />

          <AccountStatusList title="可抓取状态" statuses={data.x.status.accounts} />

          <AdvancedSection
            title="高级参数"
            description="Headless、等待时间、旧帖阈值、镜像列表都放在这里，默认折叠。"
          >
            <div className="grid gap-4 xl:grid-cols-2">
              <CheckboxField
                label="排除旧帖子"
                hint="默认开启。超过阈值的置顶帖会被过滤，不再反复抓回。"
                checked={data.x.config.excludeOldPosts}
                onChange={(value) =>
                  setXConfig((current) => ({ ...current, excludeOldPosts: value }))
                }
              />
              <CheckboxField
                label="Headless"
                hint="X 默认保持无头抓取。"
                checked={data.x.config.headless}
                onChange={(value) => setXConfig((current) => ({ ...current, headless: value }))}
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <SectionField label="页面等待（秒）" hint="公开页面加载与提取的基础等待时间。">
                <Input
                  type="number"
                  min={0}
                  step="0.5"
                  value={String(data.x.config.pageWaitSec)}
                  onChange={(event) =>
                    setXConfig((current) => ({
                      ...current,
                      pageWaitSec: Number.parseFloat(event.target.value || "0") || 0,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="旧帖阈值（天）" hint="超过这个天数的帖子会被视为旧帖并跳过。">
                <Input
                  type="number"
                  min={1}
                  max={30}
                  value={String(data.x.config.maxPostAgeDays)}
                  onChange={(event) =>
                    setXConfig((current) => ({
                      ...current,
                      maxPostAgeDays: Number.parseInt(event.target.value || "5", 10) || 5,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="账号间基础间隔（秒）" hint="多个 X 账号顺序抓取时的基础等待。">
                <Input
                  type="number"
                  min={0}
                  step="0.5"
                  value={String(data.x.config.interAccountDelaySec)}
                  onChange={(event) =>
                    setXConfig((current) => ({
                      ...current,
                      interAccountDelaySec: Number.parseFloat(event.target.value || "0") || 0,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="随机抖动（秒）" hint="叠加在基础等待上。">
                <Input
                  type="number"
                  min={0}
                  step="0.5"
                  value={String(data.x.config.interAccountDelayJitterSec)}
                  onChange={(event) =>
                    setXConfig((current) => ({
                      ...current,
                      interAccountDelayJitterSec:
                        Number.parseFloat(event.target.value || "0") || 0,
                    }))
                  }
                />
              </SectionField>
              <SectionField label="公开镜像列表" hint="每行一个实例地址，按顺序尝试。">
                <textarea
                  value={data.x.config.nitterInstances.join("\n")}
                  onChange={(event) =>
                    setXConfig((current) => ({
                      ...current,
                      nitterInstances: event.target.value
                        .split(/\r?\n/)
                        .map((item) => item.trim())
                        .filter(Boolean),
                    }))
                  }
                  className={cn(
                    "min-h-[144px] w-full rounded-[24px] border border-[color:var(--border-strong)] bg-[color:var(--paper)] px-4 py-3 text-sm text-[color:var(--ink)] outline-none transition placeholder:text-[color:var(--soft-ink)] focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color:rgba(181,106,59,0.15)]",
                  )}
                />
              </SectionField>
            </div>
          </AdvancedSection>
        </CardContent>
      </Card>
    </div>
  );
}
