import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  // Robot credentials and firmware stay on the host, outside deployable artifacts.
  outputFileTracingExcludes: { "/*": ["./robot_code/**/*"] },
};

export default nextConfig;
