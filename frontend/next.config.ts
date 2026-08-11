import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle alongside the normal build. The
  // container image copies only that, so it ships without a build toolchain or
  // dev dependencies. `next dev` and `next start` are unaffected.
  output: "standalone",
};

export default nextConfig;
