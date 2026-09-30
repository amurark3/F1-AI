import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The live timing page was folded into the command centre, which shows the
  // timing tower while a session is live. Old links land there instead.
  redirects: () =>
    Promise.resolve([
      { source: "/live", destination: "/race-control", permanent: false },
      { source: "/race-control/live", destination: "/race-control", permanent: false },
    ]),
};

export default nextConfig;
