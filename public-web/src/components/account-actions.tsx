"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Bell, BellOff } from "lucide-react";

export function AccountSubscriptionButton({
  accountId,
  subscribed,
}: {
  accountId: string;
  subscribed: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function submit() {
    setError(null);
    startTransition(async () => {
      const response = await fetch(`/api/accounts/${accountId}/subscription`, {
        method: subscribed ? "DELETE" : "POST",
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(payload.message || "操作失败");
        return;
      }
      router.refresh();
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
