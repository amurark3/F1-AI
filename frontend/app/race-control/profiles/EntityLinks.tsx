"use client";

import Link from "next/link";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { driverHref, teamHref } from "@/app/lib/entityLinks";
import { fetcher } from "@/app/utils/fetcher";

import { profilesUrl, resolveDriverId, resolveTeamId, type DriverQuery, type SeasonDirectory } from "./profilesModel";

import type { ReactNode } from "react";

/** The line-up changes on driver moves, not on race day: fetch once, keep it. */
const DIRECTORY_SWR = {
  revalidateOnFocus: false,
  revalidateIfStale: false,
  dedupingInterval: 3_600_000,
} as const;

/**
 * This season's drivers and teams by f1db id, shared by every link on a page.
 * SWR dedupes the key, so a table of fifty links makes one request.
 */
export function useSeasonDirectory(): SeasonDirectory | undefined {
  const year = new Date().getFullYear();
  const { data } = useSWR<SeasonDirectory, Error>(profilesUrl(API_BASE, year, "directory"), fetcher, DIRECTORY_SWR);
  return data;
}

interface LinkProps {
  children: ReactNode;
  className?: string;
}

const LINK_CLASS = "hover:underline decoration-white/40 underline-offset-2";

/**
 * A driver's name, linked to their page when they raced this season.
 *
 * Anyone who did not — a past champion, a feed's unknown entry — stays plain
 * text, so a link never leads to a page that does not exist.
 */
export function DriverLink({ children, className = "", ...query }: LinkProps & DriverQuery) {
  const driverId = resolveDriverId(useSeasonDirectory(), query);
  if (!driverId) return <span className={className}>{children}</span>;
  return (
    <Link href={driverHref(driverId)} className={`${LINK_CLASS} ${className}`}>
      {children}
    </Link>
  );
}

/** A team's name, linked to its page when it is on this season's grid. */
export function TeamLink({
  children,
  className = "",
  id,
  name,
}: LinkProps & { id?: string | null; name?: string | null }) {
  const teamId = resolveTeamId(useSeasonDirectory(), { id, name });
  if (!teamId) return <span className={className}>{children}</span>;
  return (
    <Link href={teamHref(teamId)} className={`${LINK_CLASS} ${className}`}>
      {children}
    </Link>
  );
}
