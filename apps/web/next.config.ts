import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: { root: process.cwd() },
  async rewrites() {
    const api = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";
    // Local-dev fallback only. In deployed environments Traefik routes these
    // path prefixes (and /admin, /static) straight to the backend; see
    // infra/traefik-dynamic.yml and infra/docker-compose.dokploy.yml.
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/ai/:path*", destination: `${api}/ai/:path*` },
      { source: "/health", destination: `${api}/health` },
    ];
  },
};

export default nextConfig;
