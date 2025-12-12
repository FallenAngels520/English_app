/** @type {import('next').NextConfig} */
const DEFAULT_BACKEND_URL = process.env.AGENT_API_BASE_URL ?? 'http://127.0.0.1:8000';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/storage/:path*',
        destination: `${DEFAULT_BACKEND_URL}/storage/:path*`
      },
      {
        source: '/media/:path*',
        destination: `${DEFAULT_BACKEND_URL}/media/:path*`
      }
    ];
  }
};

module.exports = nextConfig;
