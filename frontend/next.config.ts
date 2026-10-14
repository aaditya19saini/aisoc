import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Proxy API + OAuth routes to FastAPI so the browser only talks to one origin.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/auth/:path*", destination: `${backend}/auth/:path*` },
    ];
  },
  // Inbox sync + classification can take a while.
  experimental: { proxyTimeout: 600_000 },
};

export default nextConfig;
