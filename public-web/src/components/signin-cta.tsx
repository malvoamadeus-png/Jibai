"use client";

import { LogIn } from "lucide-react";

export function SignInCta({
  onLogin,
  compact = false,
}: {
  onLogin: () => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "login-note" : "login-note login-note-large"}>
      <div>
        <p className="font-semibold text-[color:var(--ink)]">登录后按你的订阅查看完整内容</p>
        <p className="mt-1 text-sm leading-6 text-[color:var(--muted-ink)]">
          未登录时只展示 1 条轻量预览，不加载完整分页和股票行情。
        </p>
      </div>
      <button className="primary-button" type="button" onClick={onLogin}>
        <LogIn size={16} />
        Google 登录
      </button>
    </div>
  );
}
