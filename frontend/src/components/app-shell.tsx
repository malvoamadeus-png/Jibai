"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookText,
  CircleDollarSign,
  Home,
  Orbit,
  Radar,
  SlidersHorizontal,
} from "lucide-react";

import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "总览", icon: Home },
  { href: "/authors", label: "按人", icon: BookText },
  { href: "/stocks", label: "按股票", icon: CircleDollarSign },
  { href: "/themes", label: "按 Theme", icon: Radar },
  { href: "/control", label: "配置", icon: SlidersHorizontal },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[color:var(--bg)] text-[color:var(--ink)]">
      <div className="mx-auto flex min-h-screen max-w-[1880px] flex-col gap-6 px-4 py-4 md:flex-row md:px-6 xl:px-8">
        <aside className="md:sticky md:top-4 md:h-[calc(100vh-2rem)] md:w-[248px] md:self-start">
          <div className="flex h-full flex-col rounded-[32px] border border-[color:var(--border)] bg-[color:var(--panel)]/95 p-5 shadow-[0_20px_60px_rgba(44,33,22,0.08)] backdrop-blur">
            <div className="mb-8 space-y-3">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-[color:var(--accent)]/14 text-[color:var(--accent-strong)]">
                <Orbit className="h-5 w-5" />
              </div>
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--soft-ink)]">
                  Research Notebook
                </p>
                <h1 className="text-2xl font-semibold leading-tight">观点时间线</h1>
                <p className="text-sm leading-6 text-[color:var(--muted-ink)]">
                  从作者、股票和主题三条线回看观点变化，也在同一站点里完成本地配置与运行。
                </p>
              </div>
            </div>

            <nav className="flex flex-col gap-2">
              {navItems.map((item) => {
                const active =
                  item.href === "/"
                    ? pathname === item.href
                    : pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "inline-flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition",
                      active
                        ? "bg-[color:var(--accent-strong)] text-[color:var(--accent-foreground)] shadow-[0_16px_32px_rgba(143,77,37,0.18)]"
                        : "text-[color:var(--muted-ink)] hover:bg-[color:var(--paper)] hover:text-[color:var(--ink)]",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        </aside>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
