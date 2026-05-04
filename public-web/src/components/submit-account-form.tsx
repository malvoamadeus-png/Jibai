"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";
import { Send } from "lucide-react";

export function SubmitAccountForm() {
  const router = useRouter();
  const [account, setAccount] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    startTransition(async () => {
      const response = await fetch("/api/accounts/request", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ account }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setMessage(payload.message || "提交失败");
        return;
      }
      setAccount("");
      setMessage("已提交");
      router.refresh();
    });
  }

  return (
    <form className="submit-row" onSubmit={onSubmit}>
      <input
        value={account}
        onChange={(event) => setAccount(event.target.value)}
        placeholder="@username 或 x.com/username"
        aria-label="X account"
      />
      <button className="primary-button" type="submit" disabled={pending}>
        <Send size={16} />
        提交
      </button>
      {message ? <span className="field-note">{message}</span> : null}
    </form>
  );
}
