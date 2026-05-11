/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      // The Tythe client posts to the route paths declared on the Python side.
      // In dev we proxy them to the uvicorn process on :8000.
      { source: "/deployments/:path*", destination: "http://127.0.0.1:8000/deployments/:path*" },
    ];
  },
};

export default nextConfig;
