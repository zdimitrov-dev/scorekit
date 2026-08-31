import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Don't auto-generate AGENTS.md/CLAUDE.md in web/ — the repo-root ones are authoritative.
  agentRules: false,
  // Hide the bottom-left dev indicator.
  devIndicators: false,
  // Pin the workspace root to web/ (a root package-lock.json for the dev launcher
  // otherwise makes Next infer the repo root and warn about multiple lockfiles).
  turbopack: { root: __dirname },
};

export default nextConfig;
