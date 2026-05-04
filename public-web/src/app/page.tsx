import Link from "next/link";
import { ArrowRight, Library, Radio, ShieldCheck } from "lucide-react";

import { getCurrentProfile } from "@/lib/auth";
import { listAccounts, listFeed } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const profile = await getCurrentProfile();
  const accounts = profile ? await listAccounts(profile) : [];
  const feed = profile ? await listFeed(profile, 6) : [];

  return (
    <main className="page">
      <section className="hero-grid">
        <div className="panel">
          <h1>X 账号观点追踪</h1>
          <p className="muted">
            登录后订阅已审批账号，时间线、股票和主题视图都会按你的订阅范围过滤。
          </p>
          {profile ? (
            <div className="submit-row">
              <Link className="primary-button" href="/accounts">
                <Library size={16} />
                账号库
              </Link>
              <Link className="secondary-button" href="/feed">
                <ArrowRight size={16} />
                我的订阅
              </Link>
            </div>
          ) : (
            <form action="/api/auth/login" method="post">
              <button className="primary-button" type="submit">
                Google 登录
              </button>
            </form>
          )}
          <div className="metric-row">
            <div className="metric">
              <Radio size={18} />
              <strong>{accounts.length}</strong>
              <span className="muted">可订阅账号</span>
            </div>
            <div className="metric">
              <Library size={18} />
              <strong>{accounts.filter((item) => item.subscribed).length}</strong>
              <span className="muted">我的订阅</span>
            </div>
            <div className="metric">
              <ShieldCheck size={18} />
              <strong>{profile?.isAdmin ? "Admin" : "User"}</strong>
              <span className="muted">当前身份</span>
            </div>
          </div>
        </div>
        <div className="panel">
          <h2>最近更新</h2>
          {feed.length ? (
            <div className="feed-list">
              {feed.slice(0, 3).map((item) => (
                <article key={item.id}>
                  <h3>@{item.username}</h3>
                  <p className="muted">{item.summary}</p>
                  <span className="status-pill">{item.date}</span>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty">暂无订阅更新</div>
          )}
        </div>
      </section>
    </main>
  );
}
