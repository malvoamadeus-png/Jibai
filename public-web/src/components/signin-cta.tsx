"use client";

import { LogIn } from "lucide-react";

import { Button } from "@/components/ui/button";

export function SignInCta({
  onLogin,
  compact = false,
  authAvailable = true,
}: {
  onLogin: () => void;
  compact?: boolean;
  authAvailable?: boolean;
}) {
  return (
    <div className={compact ? "login-note" : "login-note login-note-large"}>
      <div>
        <p className="font-semibold text-[color:var(--ink)]">登录后按你的订阅查看完整内容</p>
        <p className="mt-1 text-sm leading-6 text-[color:var(--muted-ink)]">
          {authAvailable
            ? "未登录时只展示 1 条轻量预览，不加载完整分页与行情视图。"
            : "Supabase Auth 当前不可用，暂时只能浏览公开预览内容。"}
        </p>
      </div>
      <Button type="button" onClick={onLogin} disabled={!authAvailable}>
        <LogIn size={16} />
        {authAvailable ? "Google 登录" : "登录暂不可用"}
      </Button>
    </div>
  );
}
