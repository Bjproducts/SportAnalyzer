import path from "node:path";
import type { NextConfig } from "next";

const isNetlify = process.env.NETLIFY === "true";
const containerOutput: Partial<NextConfig> = isNetlify
  ? {}
  : {
      // The Docker production image consumes Next's standalone server bundle.
      output: "standalone",
    };

const nextConfig: NextConfig = {
  ...containerOutput,
  reactStrictMode: true,
  // Prevent an unrelated lockfile higher in the user's directory tree from
  // becoming the trace root locally or on monorepo build hosts.
  outputFileTracingRoot: path.join(__dirname),
  poweredByHeader: false,
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    // Never ship a build that does not type-check.
    ignoreBuildErrors: false,
  },
  images: {
    remotePatterns: [
      // Provider-hosted crests and player photos.
      { protocol: "https", hostname: "media.api-sports.io" },
    ],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
