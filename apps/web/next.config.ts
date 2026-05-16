import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@quarrel/shared", "@quarrel/ai", "@quarrel/personas"],
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
