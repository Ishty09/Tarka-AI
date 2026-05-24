import { withSentryConfig } from "@sentry/nextjs";
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
  // ESLint runs in CI / locally via `pnpm lint`. Don't block prod builds on
  // it — keeps deploys fast and decoupled from minor style nits. Re-enable
  // (or set ignoreDuringBuilds: false) once the existing warnings are cleaned.
  eslint: {
    ignoreDuringBuilds: true,
  },
};

// Sentry wraps the config to: forward errors to the SDK, upload source maps
// when SENTRY_AUTH_TOKEN is set, and route browser requests through the
// tunnel route so ad-blockers don't drop telemetry. Disabled features:
//   - widenClientFileUpload: source map upload only for current build
//   - reactComponentAnnotation: noisy for our component count
//
// When SENTRY_AUTH_TOKEN is unset (local dev, fork builds) `silent: true`
// keeps the wrapper quiet and skips the upload step.
const withSentry = (cfg: NextConfig): NextConfig =>
  withSentryConfig(cfg, {
    org: process.env.SENTRY_ORG,
    project: process.env.SENTRY_PROJECT,
    authToken: process.env.SENTRY_AUTH_TOKEN,
    silent: !process.env.SENTRY_AUTH_TOKEN,
    tunnelRoute: "/monitoring",
    disableLogger: true,
    automaticVercelMonitors: false,
  });

export default withSentry(withNextIntl(nextConfig));
