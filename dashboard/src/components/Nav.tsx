"use client";

import {
  ChartLine,
  Home,
  Layers,
  Menu,
  MessageCircleQuestion,
  Store,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";
import { WeekSelector } from "./WeekSelector";

// WeekSelector reads useSearchParams(), so it must sit behind a Suspense
// boundary — otherwise Next.js refuses to statically prerender any page
// that includes the Nav (build fails with "missing-suspense-with-csr-bailout").
function WeekSelectorBoundary() {
  return (
    <Suspense fallback={<div className="h-8 w-[220px]" aria-hidden />}>
      <WeekSelector />
    </Suspense>
  );
}

const items: { href: string; label: string; icon: ReactNode }[] = [
  { href: "/", label: "Übersicht", icon: <Home className="h-4 w-4" /> },
  { href: "/stores", label: "Märkte", icon: <Store className="h-4 w-4" /> },
  { href: "/categories", label: "Kategorien", icon: <Layers className="h-4 w-4" /> },
  { href: "/deals", label: "Deal score", icon: <ChartLine className="h-4 w-4" /> },
  { href: "/ask", label: "Fragen", icon: <MessageCircleQuestion className="h-4 w-4" /> },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the drawer whenever the route changes.
  useEffect(() => setOpen(false), [pathname]);

  // Prevent body scroll while the drawer is open on mobile.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur supports-[backdrop-filter]:bg-surface/60">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-accent/15 text-accent">
            <ChartLine className="h-4 w-4" />
          </span>
          <span className="hidden xs:inline sm:inline">AngebotsBot</span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-1 md:flex">
          {items.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition ${
                  active
                    ? "bg-surface-hover text-fg"
                    : "text-fg-muted hover:bg-surface-hover hover:text-fg"
                }`}
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            );
          })}
          <div className="ml-2">
            <WeekSelectorBoundary />
          </div>
          <div className="ml-1">
            <ThemeToggle />
          </div>
        </div>

        {/* Mobile controls */}
        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            aria-label={open ? "Menü schließen" : "Menü öffnen"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </nav>

      {/* Mobile drawer */}
      {open && (
        <div className="md:hidden">
          {/* Backdrop */}
          <button
            type="button"
            aria-label="Menü schließen"
            onClick={() => setOpen(false)}
            className="fixed inset-x-0 bottom-0 top-[57px] z-20 bg-bg/60 backdrop-blur-sm"
          />
          {/* Panel */}
          <div className="absolute inset-x-0 top-full z-30 border-b border-border bg-surface shadow-lg">
            <div className="mx-auto flex max-w-6xl flex-col gap-1 px-3 py-3">
              {items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`inline-flex items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                      active
                        ? "bg-surface-hover text-fg"
                        : "text-fg-muted hover:bg-surface-hover hover:text-fg"
                    }`}
                  >
                    {item.icon}
                    {item.label}
                  </Link>
                );
              })}
              <div className="mt-2 border-t border-border pt-3">
                <WeekSelectorBoundary />
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
