import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth-context";
import { Nav } from "@/components/nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "Jibai Public",
  description: "Public X account insight tracker",
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
      </body>
    </html>
  );
}
