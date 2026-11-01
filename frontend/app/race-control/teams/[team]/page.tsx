import { redirect } from "next/navigation";

import { teamHref } from "@/app/lib/entityLinks";

interface TeamPageProps {
  params: Promise<{ team: string }>;
}

/**
 * The old team detail URL. Team slugs were built from display names, which
 * match f1db's constructor ids for every current team, so the slug carries over.
 */
export default async function TeamDetailRedirect({ params }: TeamPageProps): Promise<never> {
  const { team } = await params;
  redirect(teamHref(team));
}
