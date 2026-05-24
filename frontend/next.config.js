/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || "http://api:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
