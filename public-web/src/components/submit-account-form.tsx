"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState, useTransition } from "react";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { submitAccount } from "@/lib/direct-data";

export function SubmitAccountForm({
  onSubmitted,
  domain = "stock",
}: {
  onSubmitted?: () => void;
  domain?: "stock" | "crypto";
}) {
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
        await submitAccount(supabase, account, domain);
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
      <Input
        value={account}
        onChange={(event) => setAccount(event.target.value)}
        placeholder="@username 或 x.com/username"
        aria-label="X account"
      />
      <Button type="submit" disabled={pending}>
        <Send size={16} />
        提交
      </Button>
      {message ? <span className="field-note">{message}</span> : null}
    </form>
  );
}
