import { getTeamsIndex } from "@/app/lib/server/profiles";

import { TeamsIndexView } from "./TeamsIndexView";

/** Reads the index on the server and hands it to the view as its seed; a failed read leaves the view to fetch. */
export async function TeamsIndexSeed({ year }: { year: number }) {
  const index = await getTeamsIndex(year);
  return <TeamsIndexView year={year} seed={index?.status === "ok" ? index : null} />;
}
