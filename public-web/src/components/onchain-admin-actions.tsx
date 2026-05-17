"use client";

import type { ReactNode } from "react";
import { useState, useTransition } from "react";
import { Check, Play, Save, X } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import {
  approveOnchainWalletRequest,
  enqueueOnchainFetch,
  rejectOnchainWalletRequest,
  updateOnchainWalletAdmin,
} from "@/lib/direct-data";

function ActionButton({
  action,
  label,
  icon,
  kind = "secondary",
  onChanged,
}: {
  action: () => Promise<void>;
  label: string;
  icon: ReactNode;
  kind?: "primary" | "secondary" | "danger";
  onChanged?: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const className = kind === "primary" ? "primary-button" : kind === "danger" ? "danger-button" : "secondary-button";

  return (
    <span className="inline-action">
      <button
        className={className}
        disabled={pending}
        type="button"
        onClick={() => {
          setError(null);
          startTransition(async () => {
            try {
              await action();
              onChanged?.();
            } catch (err) {
              setError(err instanceof Error ? err.message : "操作失败");
            }
          });
        }}
      >
        {icon}
        {label}
      </button>
      {error ? <span className="field-error">{error}</span> : null}
    </span>
  );
}

export function OnchainApproveButton({ requestId, onChanged }: { requestId: string; onChanged?: () => void }) {
  const { supabase } = useAuth();
  return (
    <ActionButton
      action={() => approveOnchainWalletRequest(supabase, requestId)}
      icon={<Check size={16} />}
      kind="primary"
      label="通过"
      onChanged={onChanged}
    />
  );
}

export function OnchainRejectButton({ requestId, onChanged }: { requestId: string; onChanged?: () => void }) {
  const { supabase } = useAuth();
  return (
    <ActionButton
      action={() => rejectOnchainWalletRequest(supabase, requestId)}
      icon={<X size={16} />}
      kind="danger"
      label="拒绝"
      onChanged={onChanged}
    />
  );
}

export function OnchainManualFetchButton({ onChanged }: { onChanged?: () => void }) {
  const { supabase } = useAuth();
  return (
    <ActionButton
      action={() => enqueueOnchainFetch(supabase)}
      icon={<Play size={16} />}
      kind="primary"
      label="手动抓取"
      onChanged={onChanged}
    />
  );
}

export function OnchainWalletSaveButton({
  walletId,
  adminLabel,
  chainKeys,
  status,
  onChanged,
}: {
  walletId: string;
  adminLabel: string;
  chainKeys: string[];
  status: string;
  onChanged?: () => void;
}) {
  const { supabase } = useAuth();
  return (
    <ActionButton
      action={() => updateOnchainWalletAdmin(supabase, walletId, adminLabel, chainKeys, status)}
      icon={<Save size={16} />}
      label="保存"
      onChanged={onChanged}
    />
  );
}
