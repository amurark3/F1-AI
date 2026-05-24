import { redirect } from "next/navigation";

export default function StandingsRedirectPage() {
  redirect("/race-control/teams");
}
