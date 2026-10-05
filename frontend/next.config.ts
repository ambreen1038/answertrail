import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets a second, separate build live beside the normal one (used to test against a throwaway backend).
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;
