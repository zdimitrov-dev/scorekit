import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Don't auto-generate AGENTS.md/CLAUDE.md in web/ — the repo-root ones are authoritative.
  agentRules: false,
  // Hide the bottom-left dev indicator.
  devIndicators: false,
};

export default nextConfig;
