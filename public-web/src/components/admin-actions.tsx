"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState, useTransition } from "react";
import { Ban, Check, Play, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { approveRequest, disableAccount, enqueueManualCrawl, rejectRequest } from "@/lib/direct-data";

function AdminButton({
  action,
  label,
  kind = "secondary",
  icon,
  onChanged,
}: {
  action: () => Promise<void>;
  label: string;
  kind?: "primary" | "secondary" | "danger";
  icon: ReactNode;
  onChanged?: () => void;
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
      <Button variant={variant} type="button" disabled={pending} onClick={submit}>
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
}: {
  onChanged?: () => void;
  domain?: "stock" | "crypto";
}) {
  const { supabase } = useAuth();
  return (
    <AdminButton
      action={() => enqueueManualCrawl(supabase, domain)}
      label="手动抓取"
      kind="primary"
      icon={<Play size={16} />}
      onChanged={onChanged}
    />
  );
}
