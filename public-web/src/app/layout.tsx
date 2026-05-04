import type { Metadata } from "next";

import { Nav } from "@/components/nav";
import { getCurrentProfile } from "@/lib/auth";

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
  const profile = await getCurrentProfile();
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-frame">
          <Nav profile={profile} />
          <div className="app-main">{children}</div>
        </div>
      </body>
    </html>
  );
}
