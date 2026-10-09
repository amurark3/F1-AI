import { RulebookView } from "./RulebookView";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "F1 Regulations Search | F1 AI",
  description:
    "Search the FIA Formula 1 sporting and technical regulations by meaning rather than exact wording, with cited article references.",
};

export default function Page() {
  return <RulebookView />;
}
