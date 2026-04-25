import type { Metadata } from "next";
import { IBM_Plex_Mono, Noto_Sans_SC } from "next/font/google";

import { AppShell } from "@/components/app-shell";
import "@/app/globals.css";

const notoSansSc = Noto_Sans_SC({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "观点时间线",
  description: "本地运行的作者、股票、Theme 观点时间线查看器与配置台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${notoSansSc.variable} ${ibmPlexMono.variable} font-[var(--font-body)] antialiased`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
