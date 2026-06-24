import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  async rewrites() {
    return [
      {
        source: '/api/v3/:path*',
        destination: 'http://127.0.0.1:8000/api/v3/:path*' // Proxy to Backend
      }
    ]
  }
};

export default nextConfig;
