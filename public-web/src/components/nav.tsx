"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";
import {
  Activity,
  Bell,
  BookText,
  CircleDollarSign,
  Grid3X3,
  Home,
  LogOut,
  Menu,
  Newspaper,
  Orbit,
  Shield,
  Sparkles,
  Tags,
  Trophy,
  UserRound,
  WalletCards,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

function domainCopy(pathname: string) {
  if (pathname.startsWith("/onchain")) {
    return {
      title: "链上",
      description: "按地址与 token 观察埋伏仓位的结构变化",
    };
  }
  if (pathname.startsWith("/crypto")) {
    return {
      title: "加密",
      description: "按作者与标的回看加密信号时间线",
    };
  }
  return {
    title: "股票",
    description: "按作者与股票回看观点、叙事与风险",
  };
}

export function Nav() {
  const pathname = usePathname();
  const { loading, profile, signIn, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const isCrypto = pathname.startsWith("/crypto");
  const isOnchain = pathname.startsWith("/onchain");
  const activeDomain = useMemo(() => domainCopy(pathname), [pathname]);
  const links = isOnchain
    ? [
        { href: "/onchain", label: "总览", icon: Home, exact: true },
        { href: "/onchain/wallets", label: "地址库 / 按人", icon: WalletCards },
        { href: "/onchain/tokens", label: "按代币", icon: Grid3X3 },
        { href: "/onchain/gmgn-labels", label: "GMGN备注生成", icon: Tags },
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
          { href: "/stocks/news", label: "新闻", icon: Newspaper, exact: true },
          { href: "/stocks/news/tracking", label: "新闻（追踪）", icon: Sparkles },
          { href: "/stocks/gold", label: "点金榜", icon: Trophy },
          { href: "/stocks/narrative", label: "叙事简报", icon: Newspaper },
          { href: "/risk", label: "顶部风险", icon: Activity },
        ];

  return (
    <>
      <div className="mobile-topbar">
        <div className="mobile-topbar-copy">
          <strong>集百</strong>
          <span>{activeDomain.description}</span>
        </div>
        <Button type="button" variant="secondary" size="icon" aria-label={open ? "关闭导航" : "打开导航"} onClick={() => setOpen((current) => !current)}>
          {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </Button>
      </div>

      {open ? <button className="sidebar-backdrop" type="button" aria-label="关闭导航" onClick={() => setOpen(false)} /> : null}

      <aside className={cn("sidebar", open && "sidebar-open")}>
        <div className="sidebar-panel">
          <div className="brand-block">
            <div className="brand-mark">
              <Orbit size={20} />
            </div>
            <div>
              <p className="eyebrow">Jibai Public</p>
              <h1 className="brand-title">集百</h1>
              <p>{activeDomain.description}</p>
            </div>
          </div>

          <div className="domain-switch" aria-label="板块切换">
            <Link href="/" className={cn("domain-switch-item", !isCrypto && !isOnchain && "domain-switch-active")} onClick={() => setOpen(false)}>
              股票
            </Link>
            <Link href="/crypto" className={cn("domain-switch-item", isCrypto && "domain-switch-active")} onClick={() => setOpen(false)}>
              加密
            </Link>
            <Link href="/onchain" className={cn("domain-switch-item", isOnchain && "domain-switch-active")} onClick={() => setOpen(false)}>
              链上
            </Link>
          </div>

          <nav className="nav-links">
            {links.map((item) => {
              const Icon = item.icon;
              const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
              return (
                <Link key={item.href} href={item.href} className={cn("nav-item", active && "nav-item-active")} onClick={() => setOpen(false)}>
                  <Icon size={16} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
            {profile?.isAdmin ? (
              <Link href={isOnchain ? "/onchain/admin" : isCrypto ? "/crypto/admin" : "/admin"} className="nav-item admin-link" onClick={() => setOpen(false)}>
                <Shield size={16} />
                <span>管理</span>
              </Link>
            ) : null}
          </nav>

          <div className="sidebar-footer">
            <div className="rounded-[24px] border border-[color:var(--border)] bg-white/56 p-4">
              <p className="eyebrow" style={{ marginBottom: 8 }}>
                {activeDomain.title}
              </p>
              <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>
                {profile ? "已登录后可查看完整订阅内容、管理个人列表与提交记录。" : "未登录时仍可浏览公开预览，登录后解锁完整时间线。"}
              </p>
            </div>

            {profile ? (
              <>
                <span className="user-chip">
                  <UserRound size={16} />
                  {profile.email}
                </span>
                <Button className="w-full justify-center" variant="secondary" type="button" onClick={signOut}>
                  <LogOut className="h-4 w-4" />
                  退出登录
                </Button>
              </>
            ) : (
              <Button className="w-full justify-center" type="button" disabled={loading} onClick={signIn}>
                Google 登录
              </Button>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
