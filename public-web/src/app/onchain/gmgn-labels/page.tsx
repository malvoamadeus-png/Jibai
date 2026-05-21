"use client";

import { AlertTriangle, Copy, Play, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { LoginRequired } from "@/components/page-states";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import {
  buildLocalGMGNLabels,
  fetchGMGNLabels,
  formatLabelEntries,
  parseTokenInput,
  type GMGNTokenError,
  type GMGNTokenResult,
} from "@/lib/gmgn-labels";

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;
const EMPTY_OUTPUT = formatLabelEntries([]);

function clampLimit(value: number) {
  return Math.max(1, Math.min(MAX_LIMIT, Math.trunc(value || DEFAULT_LIMIT)));
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <Button type="button" variant="secondary" size="sm" onClick={copy}>
      <Copy className="h-4 w-4" />
      {copied ? "已复制" : label}
    </Button>
  );
}

export default function GMGNLabelsPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [tokenText, setTokenText] = useState("");
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [evmExisting, setEvmExisting] = useState("");
  const [solExisting, setSolExisting] = useState("");
  const [results, setResults] = useState<GMGNTokenResult[]>([]);
  const [apiErrors, setApiErrors] = useState<GMGNTokenError[]>([]);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const tokens = useMemo(() => parseTokenInput(tokenText), [tokenText]);
  const localOutput = useMemo(() => {
    try {
      const labels = buildLocalGMGNLabels(results, evmExisting, solExisting);
      return {
        evmText: formatLabelEntries(labels.evm),
        solText: formatLabelEntries(labels.solana),
        parseError: null as string | null,
        evmCount: labels.evm.length,
        solCount: labels.solana.length,
      };
    } catch (parseError) {
      return {
        evmText: EMPTY_OUTPUT,
        solText: EMPTY_OUTPUT,
        parseError: parseError instanceof Error ? parseError.message : "原备注 JSON 解析失败",
        evmCount: 0,
        solCount: 0,
      };
    }
  }, [evmExisting, results, solExisting]);

  if (loading) return null;
  if (!profile) return <LoginRequired onLogin={signIn} />;

  async function generate() {
    setError(null);
    setStatusText("");
    setApiErrors([]);
    const safeTokens = parseTokenInput(tokenText);
    if (!safeTokens.length) {
      setError("请至少输入一个 token address。");
      return;
    }
    if (safeTokens.length > 50) {
      setError("单次最多查询 50 个 token。");
      return;
    }
    const { data } = await supabase.auth.getSession();
    const accessToken = data.session?.access_token;
    if (!accessToken) {
      setError("登录状态已过期，请重新登录。");
      return;
    }

    setGenerating(true);
    try {
      const payload = await fetchGMGNLabels(safeTokens, clampLimit(limit), accessToken);
      setResults(payload.results || []);
      setApiErrors(payload.errors || []);
      setStatusText(`完成 ${payload.results?.length || 0} 个 token，失败 ${payload.errors?.length || 0} 个。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败，请稍后再试。");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>GMGN备注生成</h1>
          <p className="muted">按 token 查询 OKX Top 持仓与盈利地址，生成可导入 GMGN 的新增备注。</p>
        </div>
      </div>

      <section className="panel gmgn-tool-head">
        <label className="field gmgn-token-field">
          <span>Token address</span>
          <textarea
            value={tokenText}
            onChange={(event) => setTokenText(event.target.value)}
            placeholder={"一行一个 token address\n0xf3525965a4ad3ca0ac13f4d2f237113691194444"}
          />
        </label>
        <div className="gmgn-action-stack">
          <label className="field">
            <span>每个榜单数量</span>
            <input
              type="number"
              min={1}
              max={MAX_LIMIT}
              value={limit}
              onChange={(event) => setLimit(clampLimit(Number(event.target.value)))}
            />
          </label>
          <Button type="button" onClick={generate} disabled={generating || !tokens.length}>
            <Play className="h-4 w-4" />
            {generating ? "生成中" : "开始生成"}
          </Button>
          <p className="muted gmgn-small">{tokens.length} 个 token，最大 {MAX_LIMIT}</p>
        </div>
      </section>

      <section className="gmgn-notice-grid">
        <div className="panel gmgn-notice">
          <ShieldCheck className="h-5 w-5" />
          <p>原有备注只在本地浏览器用于去重，不会上传到服务器，其他人无法获取你的备注内容。</p>
        </div>
        <div className="panel gmgn-warning">
          <AlertTriangle className="h-5 w-5" />
          <p>如果不粘贴原备注，新生成备注导入 GMGN 时可能覆盖已有重复地址备注。</p>
        </div>
      </section>

      {error ? <div className="empty field-error">{error}</div> : null}
      {localOutput.parseError ? <div className="empty field-error">原备注格式错误：{localOutput.parseError}</div> : null}
      {statusText ? <div className="empty field-note">{statusText}</div> : null}
      {apiErrors.length ? (
        <section className="empty">
          <strong>部分 token 查询失败</strong>
          <div className="gmgn-error-list">
            {apiErrors.map((item) => (
              <p key={item.inputToken}>
                {item.inputToken}: {item.message}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      <section className="gmgn-workspace">
        <div className="panel gmgn-column">
          <div>
            <h2>原有备注</h2>
            <p className="muted">粘贴 GMGN 当前导出的备注，用于本地跳过已有地址。</p>
          </div>
          <label className="field gmgn-json-field">
            <span>EVM 原备注</span>
            <textarea value={evmExisting} onChange={(event) => setEvmExisting(event.target.value)} placeholder="Label-evm.txt JSON 数组" />
          </label>
          <label className="field gmgn-json-field">
            <span>Solana 原备注</span>
            <textarea value={solExisting} onChange={(event) => setSolExisting(event.target.value)} placeholder="Label-sol.txt JSON 数组" />
          </label>
        </div>

        <div className="panel gmgn-column">
          <div className="gmgn-result-head">
            <div>
              <h2>新增结果</h2>
              <p className="muted">只包含本次新增地址，不复制旧备注全量内容。</p>
            </div>
          </div>
          <label className="field gmgn-json-field">
            <span>NewLabel-evm · {localOutput.evmCount} 个</span>
            <textarea readOnly value={localOutput.evmText} />
            <CopyButton text={localOutput.evmText} label="复制 EVM" />
          </label>
          <label className="field gmgn-json-field">
            <span>NewLabel-sol · {localOutput.solCount} 个</span>
            <textarea readOnly value={localOutput.solText} />
            <CopyButton text={localOutput.solText} label="复制 Solana" />
          </label>
        </div>
      </section>
    </main>
  );
}
