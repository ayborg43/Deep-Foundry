import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Don't strip trailing slashes. Otherwise /admin/ → 308 /admin, which the
  // proxied Django then 301s back to /admin/ (APPEND_SLASH) — an infinite
  // redirect loop. Letting the slash pass through hands Django /admin/ directly.
  skipTrailingSlashRedirect: true,
  turbopack: { root: process.cwd() },
  async rewrites() {
    const api = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/ai/:path*", destination: `${api}/ai/:path*` },
      { source: "/health", destination: `${api}/health` },
      // Django admin + its static assets (served by WhiteNoise on the backend).
      { source: "/admin/:path*", destination: `${api}/admin/:path*` },
      { source: "/static/:path*", destination: `${api}/static/:path*` },
    ];
  },
};

export default nextConfig;
