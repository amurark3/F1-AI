"use client";

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { href: '/', label: 'Pit Wall' },
  { href: '/predictions', label: 'Predictions' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/standings', label: 'Standings' },
];

export default function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <main className="min-h-screen bg-neutral-950 text-white">
      {/* Header */}
      <div className="border-b border-neutral-800/80 bg-neutral-950/90 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <span className="text-2xl font-black italic tracking-tighter uppercase">
              F1 <span className="text-red-600">AI</span>
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden sm:flex items-center gap-1">
            {NAV_ITEMS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`px-3 md:px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider transition-all ${
                  pathname === href
                    ? 'bg-red-600 text-white'
                    : 'text-gray-500 hover:text-white hover:bg-neutral-800'
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="sm:hidden p-2 -mr-2 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile dropdown nav */}
        {mobileMenuOpen && (
          <div className="sm:hidden border-t border-neutral-800/60 bg-neutral-950 px-4 pb-3 pt-2 space-y-1">
            {NAV_ITEMS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileMenuOpen(false)}
                className={`block px-3 py-2.5 rounded-lg text-sm font-bold uppercase tracking-wider transition-all ${
                  pathname === href
                    ? 'bg-red-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-neutral-800'
                }`}
              >
                {label}
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Page content */}
      {children}
    </main>
  );
}
