"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, BookText, CircleDollarSign, Grid3X3, Home, LogOut, Orbit, Shield, UserRound } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

export function Nav() {
  const pathname = usePathname();
  const { loading, profile, signIn, signOut } = useAuth();
  const links = [
    { href: "/", label: "总览", icon: Home },
    { href: "/accounts", label: "账号库", icon: BookText },
    { href: "/feed", label: "我的订阅", icon: Bell },
    { href: "/stocks", label: "按股票（详情）", icon: CircleDollarSign, exact: true },
    { href: "/stocks/overview", label: "按股票（一览表）", icon: Grid3X3 },
    { href: "/risk", label: "顶部风险", icon: Activity },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-panel">
        <div className="brand-block">
          <div className="brand-mark">
            <Orbit size={20} />
          </div>
          <div>
            <p className="eyebrow">一把抓住、顷刻炼化</p>
            <h1 className="brand-title">集百</h1>
            <p>订阅已审批 X 账号，按作者和股票回看观点变化。</p>
          </div>
        </div>

        <nav className="nav-links">
          {links.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" || item.exact ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={cn("nav-item", active && "nav-item-active")}>
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
              <button className="icon-button" type="button" aria-label="退出登录" onClick={signOut}>
                <LogOut size={17} />
              </button>
            </>
          ) : (
            <button className="primary-button" type="button" disabled={loading} onClick={signIn}>
              Google 登录
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
