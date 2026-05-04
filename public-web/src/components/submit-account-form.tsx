"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";
import { Send } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { submitAccount } from "@/lib/direct-data";

export function SubmitAccountForm({ onSubmitted }: { onSubmitted?: () => void }) {
  const router = useRouter();
  const { supabase } = useAuth();
  const [account, setAccount] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    startTransition(async () => {
      try {
        await submitAccount(supabase, account);
        setAccount("");
        setMessage("已提交");
        onSubmitted?.();
        router.refresh();
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "提交失败");
      }
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
