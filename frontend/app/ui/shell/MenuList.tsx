import Link from "next/link";

import { ariaCurrent, type NavLink } from "./navConfig";

const pad = (n: number) => String(n).padStart(2, "0");

interface MenuListProps {
  links: readonly NavLink[];
  /** The page's path, so its section reads as current. Left out where no screen is current (the 404). */
  pathname?: string;
  /** Number the 404's index rows from this point. The drawer uses concise descriptions instead. */
  first?: number;
  onNavigate?: () => void;
}

/**
 * Link rows for the mobile drawer and the 404's numbered index.
 */
export function MenuList({ links, pathname, first, onNavigate }: MenuListProps) {
  const List = first === undefined ? "ul" : "ol";
  return (
    <List className={first === undefined ? undefined : "border-t border-rc-line"}>
      {links.map((link, i) => {
        const here = pathname === undefined ? undefined : ariaCurrent(link, pathname);
        return (
          <li key={link.href} className="border-b border-rc-line-soft">
            <Link
              href={link.href}
              aria-current={here}
              onClick={onNavigate}
              className={
                first === undefined
                  ? `group relative flex items-baseline justify-between gap-3 py-3 ${here ? "pl-3 before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-f1-red" : ""}`
                  : "group grid grid-cols-[40px_1fr] items-baseline py-4"
              }
            >
              {first !== undefined && (
                <span className="font-mono text-xs font-semibold text-rc-ink-3">{pad(first + i)}</span>
              )}
              <span
                className={`${first === undefined ? "text-[15px] font-semibold" : "font-display text-[28px] font-extrabold uppercase leading-none"} ${here ? "text-rc-ink" : "text-rc-ink-2 group-hover:text-rc-ink"}`}
              >
                {link.label}
              </span>
              {first === undefined && (
                <span className="max-w-[58%] text-right text-xs text-rc-ink-3">{link.description}</span>
              )}
            </Link>
          </li>
        );
      })}
    </List>
  );
}
