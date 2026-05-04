import { LogIn } from "lucide-react";

export function LoadingPanel({ label = "加载中" }: { label?: string }) {
  return (
    <main className="page">
      <div className="empty">{label}</div>
    </main>
  );
}

export function LoginRequired({ onLogin }: { onLogin: () => void }) {
  return (
    <main className="page">
      <section className="panel">
        <h1>请先登录</h1>
        <p className="muted">登录后可以订阅已审批账号、提交新账号并查看自己的时间线。</p>
        <button className="primary-button" type="button" onClick={onLogin}>
          <LogIn size={16} />
          Google 登录
        </button>
      </section>
    </main>
  );
}
