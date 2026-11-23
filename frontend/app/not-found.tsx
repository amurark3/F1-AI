import { PageHero } from "./ui/PageHero";
import { MenuList } from "./ui/shell/MenuList";
import { COMMAND_CENTER_LINK, ENGINEER_LINK, NAV_GROUPS } from "./ui/shell/navConfig";
import { EYEBROW } from "./ui/typography";

/**
 * The 404 for any unknown address, and for a page that calls `notFound()`
 * (an unknown driver, team, car or season). It sits in the usual shell, and
 * lists every screen from `navConfig` in the same order as the drawer.
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
        className="mt-14 grid gap-x-16 gap-y-10 motion-safe:animate-fade-up [animation-delay:300ms]"
      >
        <MenuList links={[COMMAND_CENTER_LINK]} first={1} />
        <div className="grid gap-x-16 gap-y-10 lg:grid-cols-3">
          {NAV_GROUPS.map((group, index) => {
            const first = 2 + NAV_GROUPS.slice(0, index).reduce((count, previous) => count + previous.links.length, 0);
            return (
              <div key={group.id}>
                <h2 className={`${EYEBROW} mb-3`}>{group.label}</h2>
                <MenuList links={group.links} first={first} />
              </div>
            );
          })}
        </div>
        <MenuList
          links={[ENGINEER_LINK]}
          first={2 + NAV_GROUPS.reduce((count, group) => count + group.links.length, 0)}
        />
      </nav>
    </>
  );
}
