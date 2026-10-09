import { EngineerView } from "./EngineerView";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Race Engineer | F1 AI",
  description:
    "Ask about Formula 1 strategy, race history, or the regulations in plain English and get answers grounded in live and historical data.",
};

export default function Page() {
  return <EngineerView />;
}
