"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState, useTransition } from "react";
import { Ban, Check, Play, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import {
  addCryptoBlockedTerm,
  adminDeleteCryptoAsset,
  approveRequest,
  disableAccount,
  enqueueManualCrawl,
  rejectRequest,
  removeCryptoBlockedTerm,
  setDomainPipelineEnabled,
} from "@/lib/direct-data";

function AdminButton({
  action,
  label,
  kind = "secondary",
  icon,
  onChanged,
  disabled = false,
}: {
  action: () => Promise<void>;
  label: string;
  kind?: "primary" | "secondary" | "danger";
  icon: ReactNode;
  onChanged?: () => void;
  disabled?: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function submit() {
    setError(null);
    startTransition(async () => {
      try {
        await action();
        onChanged?.();
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "操作失败");
      }
    });
  }

  const variant = kind === "primary" ? "primary" : kind === "danger" ? "destructive" : "secondary";
  return (
    <span className="inline-action">
      <Button variant={variant} type="button" disabled={pending || disabled} onClick={submit}>
        {icon}
        {label}
      </Button>
      {error ? <span className="field-error">{error}</span> : null}
    </span>
  );
}

export function ApproveButton({ requestId, onChanged }: { requestId: string; onChanged?: () => void }) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => approveRequest(supabase, requestId)}
      label="通过"
      kind="primary"
      icon={<Check size={16} />}
      onChanged={onChanged}
    />
  );
}

export function RejectButton({ requestId, onChanged }: { requestId: string; onChanged?: () => void }) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => rejectRequest(supabase, requestId)}
      label="拒绝"
      kind="danger"
      icon={<X size={16} />}
      onChanged={onChanged}
    />
  );
}

export function DisableButton({
  accountId,
  onChanged,
  domain = "stock",
}: {
  accountId: string;
  onChanged?: () => void;
  domain?: "stock" | "crypto";
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => disableAccount(supabase, accountId, domain)}
      label="禁用"
      kind="danger"
      icon={<Ban size={16} />}
      onChanged={onChanged}
    />
  );
}

export function ManualRunButton({
  onChanged,
  domain = "stock",
  disabled = false,
}: {
  onChanged?: () => void;
  domain?: "stock" | "crypto";
  disabled?: boolean;
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => enqueueManualCrawl(supabase, domain)}
      label="手动抓取"
      kind="primary"
      icon={<Play size={16} />}
      onChanged={onChanged}
      disabled={disabled}
    />
  );
}

export function ToggleDomainPipelineButton({
  domain,
  enabled,
  onChanged,
}: {
  domain: "stock" | "crypto";
  enabled: boolean;
  onChanged?: () => void;
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={async () => {
        await setDomainPipelineEnabled(supabase, domain, !enabled);
      }}
      label={enabled ? "关闭运行" : "恢复运行"}
      kind={enabled ? "danger" : "primary"}
      icon={enabled ? <Ban size={16} /> : <Play size={16} />}
      onChanged={onChanged}
    />
  );
}

export function AddCryptoBlockedTermButton({
  term,
  onChanged,
}: {
  term: string;
  onChanged?: () => void;
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => addCryptoBlockedTerm(supabase, term)}
      label="添加屏蔽词"
      kind="primary"
      icon={<Ban size={16} />}
      onChanged={onChanged}
    />
  );
}

export function RemoveCryptoBlockedTermButton({
  term,
  onChanged,
}: {
  term: string;
  onChanged?: () => void;
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => removeCryptoBlockedTerm(supabase, term)}
      label="移除"
      kind="danger"
      icon={<X size={16} />}
      onChanged={onChanged}
    />
  );
}

export function DeleteCryptoAssetButton({
  assetKey,
  reason = "deleted_by_admin",
  label = "删除标的",
  onChanged,
}: {
  assetKey: string;
  reason?: string;
  label?: string;
  onChanged?: () => void;
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => adminDeleteCryptoAsset(supabase, assetKey, reason)}
      label={label}
      kind="danger"
      icon={<Trash2 size={16} />}
      onChanged={onChanged}
    />
  );
}
