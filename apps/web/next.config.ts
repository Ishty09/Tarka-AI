import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// next-intl resolves the user's locale + loads the matching messages
// bundle via i18n/request.ts on every server render.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@quarrel/shared", "@quarrel/ai", "@quarrel/personas"],
  experimental: {
    typedRoutes: true,
  },
};

export default withNextIntl(nextConfig);
