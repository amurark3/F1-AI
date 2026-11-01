import { redirect } from "next/navigation";

/** Rival Intel became Teams & Drivers; its standings read lives on each team page. */
export default function IntelPage(): never {
  redirect("/race-control/constructors");
}
