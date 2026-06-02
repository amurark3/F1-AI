"use client";

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const NAV_ITEMS = [
  { href: '/',            label: 'Workspaces' },
  { href: '/race-control',label: 'Race Control' },
  { href: '/consumer',    label: 'Consumer' },
  { href: '/strategy',    label: 'Strategy HQ' },
  { href: '/calendar',   label: 'Calendar' },
  { href: '/standings',  label: 'Standings' },
  { href: '/predictions',label: 'Predictions' },
  { href: '/live',       label: 'Live',      live: true },
];

export default function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (pathname?.startsWith('/race-control')) {
    return <>{children}</>;
  }

  return (
    <main className="min-h-screen" style={{ background: '#080808' }}>
      {/* ── Top speed stripe ─────────────────────── */}
      <div
        className="h-[3px] relative overflow-hidden"
        style={{ background: 'linear-gradient(90deg, #E10600 0%, #FF4422 50%, #E10600 100%)' }}
      >
        {/* animated shimmer */}
        <div
          className="absolute inset-y-0 w-1/3 animate-streak"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent)' }}
        />
      </div>

      {/* ── Header ──────────────────────────────────── */}
      <header className="glass-strong border-b border-white/5 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center h-14">

          {/* Logo */}
          <Link href="/" className="flex items-center shrink-0 mr-6 sm:mr-10 group">
            <span
              className="text-[22px] font-black italic tracking-tighter uppercase leading-none select-none"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              <span className="text-white">F1</span>
              <span className="ml-1" style={{ color: '#E10600' }}>AI</span>
            </span>
            {/* underline speeds in on hover */}
            <span
              className="absolute bottom-0 left-0 h-[2px] w-0 group-hover:w-full transition-all duration-300"
              style={{ background: '#E10600' }}
            />
          </Link>

          {/* ── Desktop tabs ──────────────────────── */}
          <nav className="hidden sm:flex items-stretch h-14 flex-1 relative">
            {NAV_ITEMS.map(({ href, label, live }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={`
                    relative flex items-center gap-1.5 px-4 md:px-5
                    text-[11px] font-black uppercase tracking-widest
                    transition-colors duration-200 border-b-2
                    ${active
                      ? 'text-white border-[#E10600]'
                      : 'text-neutral-500 border-transparent hover:text-neutral-200 hover:border-white/20'
                    }
                  `}
                  style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                >
                  {label}
                  {live && (
                    <span
                      className="h-[7px] w-[7px] rounded-full animate-glow-pulse"
                      style={{ background: '#E10600' }}
                    />
                  )}
                  {/* animated underline indicator */}
                  {active && (
                    <motion.span
                      layoutId="nav-indicator"
                      className="absolute bottom-[-1px] left-0 right-0 h-[2px]"
                      style={{ background: '#E10600' }}
                      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                    />
                  )}
                </Link>
              );
            })}
          </nav>

          {/* ── Mobile hamburger ──────────────────── */}
          <button
            onClick={() => setMobileOpen(v => !v)}
            className="sm:hidden ml-auto p-2 -mr-2 rounded-lg text-neutral-400 hover:text-white hover:bg-white/8 transition-all"
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* ── Mobile dropdown ───────────────────── */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="sm:hidden overflow-hidden border-t border-white/5"
            >
              <div className="glass-strong px-4 pb-3 pt-1 space-y-0.5">
                {NAV_ITEMS.map(({ href, label, live }) => {
                  const active = pathname === href;
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMobileOpen(false)}
                      className={`
                        flex items-center justify-between px-3 py-3 rounded-lg
                        text-xs font-black uppercase tracking-widest
                        transition-all duration-150 border-l-2
                        ${active
                          ? 'text-white border-[#E10600] bg-white/4'
                          : 'text-neutral-500 border-transparent hover:text-white hover:bg-white/3'
                        }
                      `}
                      style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                    >
                      {label}
                      {live && (
                        <span
                          className="h-[7px] w-[7px] rounded-full animate-glow-pulse"
                          style={{ background: '#E10600' }}
                        />
                      )}
                    </Link>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {children}
    </main>
  );
}
