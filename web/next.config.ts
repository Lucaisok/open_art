import type { NextConfig } from "next";
import { API_URL } from "./lib/config";

const nextConfig: NextConfig = {
  poweredByHeader: false,

  // The browser only ever talks to this site: every /api/* request is forwarded to
  // FastAPI. One origin means the session cookie works without any CORS setup.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
