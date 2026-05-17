"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, BookText, CircleDollarSign, Grid3X3, Home, LogOut, Orbit, Shield, UserRound, WalletCards } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

export function Nav() {
  const pathname = usePathname();
  const { loading, profile, signIn, signOut } = useAuth();
  const isCrypto = pathname.startsWith("/crypto");
  const isOnchain = pathname.startsWith("/onchain");
  const links = isOnchain
    ? [
        { href: "/onchain", label: "总览", icon: Home, exact: true },
        { href: "/onchain/wallets", label: "地址库 / 按人", icon: WalletCards },
        { href: "/onchain/tokens", label: "按代币", icon: Grid3X3 },
      ]
    : isCrypto
    ? [
        { href: "/crypto", label: "总览", icon: Home, exact: true },
        { href: "/crypto/accounts", label: "账号库", icon: BookText },
        { href: "/crypto/feed", label: "我的订阅", icon: Bell },
        { href: "/crypto/assets", label: "按标的（详情）", icon: CircleDollarSign, exact: true },
        { href: "/crypto/assets/overview", label: "按标的（一览表）", icon: Grid3X3 },
      ]
    : [
        { href: "/", label: "总览", icon: Home, exact: true },
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
            <p>
              {isOnchain
                ? "追踪已审批链上地址，按 token 和地址回看埋伏持仓变化。"
                : isCrypto
                  ? "订阅已审批 X 账号，按作者和 crypto 标的回看信号变化。"
                  : "订阅已审批 X 账号，按作者和股票回看观点变化。"}
            </p>
          </div>
        </div>

        <div className="domain-switch" aria-label="板块切换">
          <Link href="/" className={cn("domain-switch-item", !isCrypto && !isOnchain && "domain-switch-active")}>
            股票
          </Link>
          <Link href="/crypto" className={cn("domain-switch-item", isCrypto && "domain-switch-active")}>
            加密
          </Link>
          <Link href="/onchain" className={cn("domain-switch-item", isOnchain && "domain-switch-active")}>
            链上
          </Link>
        </div>

        <nav className="nav-links">
          {links.map((item) => {
            const Icon = item.icon;
            const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={cn("nav-item", active && "nav-item-active")}>
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            );
          })}
          {profile?.isAdmin ? (
            <Link href={isOnchain ? "/onchain/admin" : isCrypto ? "/crypto/admin" : "/admin"} className="nav-item admin-link">
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
