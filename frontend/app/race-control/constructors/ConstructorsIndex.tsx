"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { teamHref } from "@/app/lib/entityLinks";
import { fetcher } from "@/app/utils/fetcher";

import { InlineNotice, PageLoader } from "../components/RaceControlPrimitives";
import { profilesUrl, type SeasonDirectory } from "../profiles/profilesModel";

/**
 * The fallback when the server could not reach the backend to pick a team:
 * fetch the season here and open the championship leader once it lands.
 */
export function ConstructorsIndex({ year }: { year: number }) {
  const router = useRouter();
  const { data, error, mutate } = useSWR<SeasonDirectory, Error>(profilesUrl(API_BASE, year, "directory"), fetcher, {
    revalidateOnFocus: false,
  });
  const leader = data?.teams[0]?.id;

  useEffect(() => {
    if (leader) {
      router.replace(teamHref(leader));
    }
  }, [leader, router]);

  if (error || (data && !leader)) {
    return (
      <InlineNotice title="Teams unavailable" tone="error">
        The {year} line-up could not be loaded.
        <button
          type="button"
          onClick={() => void mutate()}
          className="ml-2 font-bold text-white underline decoration-white/30"
        >
          Retry
        </button>
      </InlineNotice>
    );
  }
  return <PageLoader title="Loading teams" detail={`Opening the ${year} championship leader.`} />;
}
