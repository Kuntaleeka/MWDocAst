import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // In dev, FastAPI runs on :8000. On Vercel, /api/*.py are Python functions.
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination:
          process.env.NODE_ENV === "development"
            ? "http://127.0.0.1:8000/api/py/:path*"
            : "/api/",
      },
    ];
  },
};

export default nextConfig;
