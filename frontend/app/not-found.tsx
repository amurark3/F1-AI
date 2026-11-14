import { PageHero } from "./ui/PageHero";
import { MenuList } from "./ui/shell/MenuList";
import { MORE_NAV, PRIMARY_NAV } from "./ui/shell/navConfig";
import { EYEBROW } from "./ui/typography";

/**
 * The 404 for any unknown address, and for a page that calls `notFound()`
 * (an unknown driver, team, car or season). It sits in the usual shell, and
 * lists every screen from `navConfig` as the way back, in the mobile menu's
 * rows: the top bar's sections, then the screens under More.
 */
export default function NotFound() {
  return (
    <>
      <PageHero
        eyebrow="Error 404"
        title="Page not found"
        meta="Nothing lives at this address. The link may be wrong, or the page may have moved. Every screen is below."
      />
      <nav
        aria-label="All screens"
        className="mt-14 grid gap-x-16 gap-y-10 motion-safe:animate-fade-up [animation-delay:300ms] lg:grid-cols-2"
      >
        <div>
          <p className={`${EYEBROW} mb-3`}>Sections</p>
          <MenuList links={PRIMARY_NAV} first={1} />
        </div>
        <div>
          <p className={`${EYEBROW} mb-3`}>More</p>
          <MenuList links={MORE_NAV} first={PRIMARY_NAV.length + 1} />
        </div>
      </nav>
    </>
  );
}
