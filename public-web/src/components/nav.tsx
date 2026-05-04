import Link from "next/link";
import { Bell, BookText, CircleDollarSign, Home, LogOut, Orbit, Radar, Shield, UserRound } from "lucide-react";

import type { UserProfile } from "@/lib/types";

export function Nav({ profile }: { profile: UserProfile | null }) {
  const links = profile
    ? [
        { href: "/", label: "总览", icon: Home },
        { href: "/accounts", label: "账号库", icon: BookText },
        { href: "/feed", label: "我的订阅", icon: Bell },
        { href: "/stocks", label: "按股票", icon: CircleDollarSign },
        { href: "/themes", label: "按 Theme", icon: Radar },
      ]
    : [{ href: "/", label: "总览", icon: Home }];

  return (
    <aside className="sidebar">
      <div className="sidebar-panel">
        <div className="brand-block">
          <div className="brand-mark">
            <Orbit size={20} />
          </div>
          <div>
            <p className="eyebrow">Research Notebook</p>
            <h1>观点时间线</h1>
            <p>订阅已审批 X 账号，按作者、股票和 Theme 回看观点变化。</p>
          </div>
        </div>

        <nav className="nav-links">
          {links.map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="nav-item">
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            );
          })}
          {profile?.isAdmin ? (
            <Link href="/admin" className="nav-item admin-link">
              <Shield size={16} />
              <span>管理</span>
            </Link>
          ) : null}
        </nav>

        <div className="sidebar-footer">
        {profile ? (
          <>
            <span className="user-chip">
              <UserRound size={16} />
              {profile.email}
            </span>
            <form action="/api/auth/logout" method="post">
              <button className="icon-button" type="submit" aria-label="退出登录">
                <LogOut size={17} />
              </button>
            </form>
          </>
        ) : (
          <form action="/api/auth/login" method="post">
            <button className="primary-button" type="submit">
              Google 登录
            </button>
          </form>
        )}
        </div>
      </div>
    </aside>
  );
}
