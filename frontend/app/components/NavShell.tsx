"use client";

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const NAV_ITEMS = [
  { href: '/', label: 'Pit Wall' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/standings', label: 'Standings' },
];

export default function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <main className="min-h-screen bg-neutral-950 text-white">
      {/* Header */}
      <div className="glass-strong border-b border-white/5 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <span className="text-2xl font-black italic tracking-tighter uppercase">
              F1 <span className="bg-gradient-to-r from-red-500 to-orange-400 bg-clip-text text-transparent">AI</span>
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden sm:flex items-center gap-1">
            {NAV_ITEMS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`px-3 md:px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider transition-all duration-300 hover:scale-105 ${
                  pathname === href
                    ? 'bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25'
                    : 'text-neutral-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="sm:hidden p-2 -mr-2 rounded-xl text-neutral-400 hover:text-white hover:bg-white/10 transition-all duration-200"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile dropdown nav */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="sm:hidden overflow-hidden border-t border-white/5"
            >
              <div className="glass-strong px-4 pb-3 pt-2 space-y-1">
                {NAV_ITEMS.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`block px-3 py-2.5 rounded-xl text-sm font-bold uppercase tracking-wider transition-all duration-200 ${
                      pathname === href
                        ? 'bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25'
                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    {label}
                  </Link>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Page content */}
      {children}
    </main>
  );
}
