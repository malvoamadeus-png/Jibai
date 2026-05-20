import { LogIn, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function LoadingPanel({ label = "加载中..." }: { label?: string }) {
  return (
    <main className="page">
      <Card variant="muted">
        <CardContent className="flex items-center gap-3 py-10">
          <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-[color:rgba(10,132,255,0.1)] text-[color:var(--accent-strong)]">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <p className="font-semibold text-[color:var(--ink)]">{label}</p>
            <p className="mt-1 text-sm text-[color:var(--muted-ink)]">正在加载页面内容，请稍候。</p>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

export function LoginRequired({ onLogin }: { onLogin: () => void }) {
  return (
    <main className="page">
      <Card variant="elevated">
        <CardHeader>
          <CardTitle className="text-4xl">请先登录</CardTitle>
          <CardDescription>
            登录后可以订阅已审批账号、提交新账号，并查看自己的完整时间线。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" onClick={onLogin}>
            <LogIn size={16} />
            Google 登录
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
