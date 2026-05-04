"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState, useTransition } from "react";
import { Check, X } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { approveRequest, rejectRequest } from "@/lib/direct-data";

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

  const className = kind === "primary" ? "primary-button" : kind === "danger" ? "danger-button" : "secondary-button";
  return (
    <span className="inline-action">
      <button className={className} type="button" disabled={pending} onClick={submit}>
        {icon}
        {label}
      </button>
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
