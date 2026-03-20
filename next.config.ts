import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Exclude worker directory from Next.js build
  typescript: {
    ignoreBuildErrors: false,
  },
  // Explicitly set the workspace root to this project's directory,
  // preventing Next.js from walking up to a parent lockfile.
  outputFileTracingRoot: path.join(__dirname, "./"),
};

export default nextConfig;
