import { RulebookView } from "./RulebookView";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rulebook | F1 AI",
  description:
    "Ask the FIA Formula 1 regulations a question: the closest articles, quoted, and the stewards' decisions that applied them.",
};

export default function Page() {
  return <RulebookView />;
}
