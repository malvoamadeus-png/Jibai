import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/gmgn-api/:path*",
        destination: "http://47.76.243.147:8010/:path*",
      },
    ];
  },
};

export default nextConfig;
