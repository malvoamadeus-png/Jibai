"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState, useTransition } from "react";
import { Check, Play, X } from "lucide-react";

function AdminButton({
  action,
  label,
  kind = "secondary",
  icon,
}: {
  action: string;
  label: string;
  kind?: "primary" | "secondary" | "danger";
  icon: ReactNode;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function submit() {
    setError(null);
    startTransition(async () => {
      const response = await fetch(action, { method: "POST" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(payload.message || "操作失败");
        return;
      }
      router.refresh();
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

export function ApproveButton({ requestId }: { requestId: string }) {
  return (
    <AdminButton
      action={`/api/admin/requests/${requestId}/approve`}
      label="通过"
      kind="primary"
      icon={<Check size={16} />}
    />
  );
}

export function RejectButton({ requestId }: { requestId: string }) {
  return <AdminButton action={`/api/admin/requests/${requestId}/reject`} label="拒绝" kind="danger" icon={<X size={16} />} />;
}

export function ManualRunButton() {
  return <AdminButton action="/api/admin/jobs/manual" label="手动运行" kind="primary" icon={<Play size={16} />} />;
}
