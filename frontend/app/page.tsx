import { HomeHero } from "./home/HomeHero";
import { HomeSections } from "./home/HomeSections";

/**
 * The landing page (docs/design/redesign/home.html).
 *
 * Static by decision (PLAN, Locked decisions: Homepage): it fetches nothing,
 * not even at build time, and shows no live or baked-in data, so `next build`
 * prerenders it (○) and it paints at once whatever the backend is doing. The
 * readiness probe in the root layout is the only API call on this route.
 * Adding a data dependency here would undo that.
 */
export default function HomePage() {
  return (
    <>
      <HomeHero />
      <HomeSections />
    </>
  );
}
