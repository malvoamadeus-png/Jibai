import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";

import { AuthProvider } from "@/lib/auth-context";
import { Nav } from "@/components/nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "集百 | Jibai Public",
  description: "公开账号洞察与主题信号浏览",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <div className="app-frame">
            <Nav />
            <div className="app-main">{children}</div>
          </div>
        </AuthProvider>
        <Analytics />
      </body>
    </html>
  );
}
