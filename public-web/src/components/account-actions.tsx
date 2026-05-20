"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Bell, BellOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { setSubscription } from "@/lib/direct-data";

export function AccountSubscriptionButton({
  accountId,
  subscribed,
  onChanged,
  domain = "stock",
}: {
  accountId: string;
  subscribed: boolean;
  onChanged?: () => void;
  domain?: "stock" | "crypto";
}) {
  const router = useRouter();
  const { loading, profile, signIn, supabase } = useAuth();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function submit() {
    setError(null);
    if (!profile) {
      void signIn();
      return;
    }
    startTransition(async () => {
      try {
        await setSubscription(supabase, profile, accountId, !subscribed, domain);
        onChanged?.();
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "操作失败");
      }
    });
  }

  return (
    <div className="inline-action">
      <Button variant={subscribed ? "secondary" : "primary"} disabled={pending || loading} onClick={submit}>
        {subscribed ? <BellOff size={16} /> : <Bell size={16} />}
        {!profile ? "登录订阅" : subscribed ? "取消订阅" : "订阅"}
      </Button>
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}
