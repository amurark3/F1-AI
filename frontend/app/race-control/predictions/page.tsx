import { redirect } from "next/navigation";

/**
 * The screen this URL served was renamed to the Grand Prix Hub.
 *
 * Predictions were only ever one of its panels — the circuit profile, session
 * schedule, starting grid and results review all live here too — so the route
 * moved to `/race-control/grand-prix`. This redirect keeps bookmarks and any
 * link shared while the old name was live from landing on a 404.
 */
export default function RaceControlPredictionsRedirectPage() {
  redirect("/race-control/grand-prix");
}
