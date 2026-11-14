import Link from "next/link";

import { ariaCurrent, type NavLink } from "./navConfig";

const pad = (n: number) => String(n).padStart(2, "0");

interface MenuListProps {
  links: readonly NavLink[];
  /** The page's path, so its section reads as current. Left out where no screen is current (the 404). */
  pathname?: string;
  /** The index numeral of the first row, so More's rows carry on from the main list. */
  first: number;
  onNavigate?: () => void;
}

/**
 * Rows in the index style (`docs/design/redesign/index.html`): a mono numeral,
 * then the title in the display face. The mobile menu and the 404 page list
 * the screens with it.
 */
export function MenuList({ links, pathname, first, onNavigate }: MenuListProps) {
  return (
    <ol className="border-t border-rc-line">
      {links.map((link, i) => {
        const here = pathname === undefined ? undefined : ariaCurrent(link, pathname);
        return (
          <li key={link.href} className="border-b border-rc-line">
            <Link
              href={link.href}
              aria-current={here}
              onClick={onNavigate}
              className="group grid grid-cols-[40px_1fr] items-baseline py-4"
            >
              <span className={`font-mono text-xs font-semibold ${here ? "text-rc-red-text" : "text-rc-ink-3"}`}>
                {pad(first + i)}
              </span>
              <span
                className={`font-display text-[28px] font-extrabold uppercase leading-none ${here ? "text-rc-ink" : "text-rc-ink-2 group-hover:text-rc-ink"}`}
              >
                {link.label}
              </span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
