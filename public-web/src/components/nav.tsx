"use client";

import Link from "next/link";
import { Bell, BookText, CircleDollarSign, Home, LogOut, Orbit, Radar, Shield, UserRound } from "lucide-react";

import { useAuth } from "@/lib/auth-context";

export function Nav() {
  const { loading, profile, signIn, signOut } = useAuth();
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
