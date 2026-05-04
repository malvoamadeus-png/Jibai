"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Bell, BellOff } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { setSubscription } from "@/lib/direct-data";

export function AccountSubscriptionButton({
  accountId,
  subscribed,
  onChanged,
}: {
  accountId: string;
  subscribed: boolean;
  onChanged?: () => void;
}) {
  const router = useRouter();
  const { profile, supabase } = useAuth();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function submit() {
    setError(null);
    startTransition(async () => {
      try {
        if (!profile) throw new Error("请先登录");
        await setSubscription(supabase, profile, accountId, !subscribed);
        onChanged?.();
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "操作失败");
      }
    });
  }

  return (
    <div className="inline-action">
      <button className={subscribed ? "secondary-button" : "primary-button"} disabled={pending} onClick={submit}>
        {subscribed ? <BellOff size={16} /> : <Bell size={16} />}
        {subscribed ? "取消订阅" : "订阅"}
      </button>
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}
