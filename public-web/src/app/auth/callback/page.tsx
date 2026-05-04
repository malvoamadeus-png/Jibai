"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState("正在完成登录");

  useEffect(() => {
    async function finishLogin() {
      const code = searchParams.get("code");
      const error = searchParams.get("error_description") || searchParams.get("error");
      if (error) {
        setMessage(error);
        return;
      }
      if (!code) {
        setMessage("缺少登录回调 code。");
        return;
      }

      const supabase = getSupabaseBrowserClient();
      const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
      if (exchangeError) {
        setMessage(exchangeError.message);
        return;
      }
      router.replace("/");
    }
    finishLogin().catch((err) => setMessage(err instanceof Error ? err.message : "登录失败"));
  }, [router, searchParams]);

  return (
    <main className="page">
      <div className="empty">{message}</div>
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="page">
          <div className="empty">正在完成登录</div>
        </main>
      }
    >
      <CallbackContent />
    </Suspense>
  );
}
