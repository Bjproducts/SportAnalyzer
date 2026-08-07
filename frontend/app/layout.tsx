import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Providers } from "./providers";
import "./globals.css";

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ??
  process.env.DEPLOY_PRIME_URL ??
  process.env.URL ??
  "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "SOT Analyzer",
    template: "%s · SOT Analyzer",
  },
  description:
    "Historical shots-on-target research for football players: match-by-match records, venue splits, streaks and consistency.",
  openGraph: {
    title: "SOT/LAB — Evidence over instinct",
    description: "Match-by-match shots-on-target research with honest sample sizes.",
    images: [{ url: "/og.png", width: 1728, height: 910, alt: "SOT/LAB — Evidence over instinct" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "SOT/LAB — Evidence over instinct",
    description: "Match-by-match shots-on-target research with honest sample sizes.",
    images: ["/og.png"],
  },
};

const NAV_LINKS = [
  { href: "/", label: "Research" },
  { href: "/upcoming", label: "Upcoming" },
  { href: "/compare", label: "Compare" },
] as const;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-ink-950 text-slate-200">
        <Providers>
          <div className="flex min-h-screen flex-col">
            <header className="sticky top-0 z-50 border-b border-white/[0.07] bg-ink-950/85 backdrop-blur-xl">
              <div className="mx-auto flex w-full max-w-7xl items-center gap-6 px-4 py-4 sm:px-6">
                <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
                  <span
                    aria-hidden
                    className="grid h-8 w-8 place-items-center rounded-lg bg-lime text-[10px] font-black text-ink-950"
                  >
                    ST
                  </span>
                  <span className="text-sm text-white">SOT<span className="text-lime">/</span>LAB</span>
                </Link>
                <nav className="flex items-center gap-1 text-sm" aria-label="Main">
                  {NAV_LINKS.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      className="rounded-lg px-3 py-1.5 text-xs text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-white"
                    >
                      {link.label}
                    </Link>
                  ))}
                </nav>
              </div>
            </header>

            <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-7 sm:px-6 md:py-10">{children}</main>

            <footer className="border-t border-white/[0.07] px-4 py-7 text-xs text-slate-600 sm:px-6">
              <div className="mx-auto flex max-w-7xl flex-col justify-between gap-2 sm:flex-row">
                <span>Historical research · Missing data is never counted as zero.</span>
                <span>Authorized provider data · Sample sizes are always shown.</span>
              </div>
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
