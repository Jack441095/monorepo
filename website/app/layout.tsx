import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Phase 5.6: nitedsp.co.uk is the approved production domain (Jack, Phase
// 5.6). Hardcoded here deliberately — unlike NEXT_PUBLIC_NITE_DSP_API_URL
// (a functional fetch target that must never point at the wrong
// environment), metadataBase/canonical/OG URLs are pure metadata about the
// site's real-world identity, safe to state directly regardless of which
// environment is currently serving the page.
//
// Uses the "www" host, not the bare apex: Railway's real custom domain (and
// this deployment's actual HTTPS target) is www.nitedsp.co.uk — the apex
// only redirects to it at the DNS/registrar level and doesn't itself serve
// HTTPS yet (docs/IONOS_DNS_SETUP.md). Update if/when that changes.
export const metadata: Metadata = {
  metadataBase: new URL("https://www.nitedsp.co.uk"),
  title: {
    default: "NITE DSP",
    template: "%s | NITE DSP",
  },
  description: "Audio production tools by NITE DSP.",
  openGraph: {
    title: "NITE DSP",
    description: "Audio production tools by NITE DSP.",
    url: "https://www.nitedsp.co.uk",
    siteName: "NITE DSP",
    type: "website",
  },
};

const ORGANIZATION_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "NITE DSP",
  url: "https://www.nitedsp.co.uk",
  email: "nitedsp@outlook.com",
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html
      lang="en"
      data-theme="c"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_JSON_LD) }}
        />
        {/* Marks JS availability before first paint so scroll-reveal hidden
            states only ever apply when they can actually be removed. */}
        <script
          dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.add('js');" }}
        />
      </head>
      <body className="min-h-full flex flex-col grain" style={{ background: "var(--background)", color: "var(--foreground)" }}>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SiteHeader />

        <main id="main" className="flex-1">
          {children}
        </main>

        <footer className="border-t mt-16" style={{ borderColor: "var(--border)" }}>
          <div
            className="mx-auto px-6 py-12 grid gap-10 sm:grid-cols-3 text-sm"
            style={{ maxWidth: "var(--content-width)", color: "var(--muted)" }}
          >
            <div>
              <div className="brand-mark text-lg text-[color:var(--foreground)]">NITE DSP</div>
              <p className="mt-2 text-xs" style={{ color: "var(--muted-dim)" }}>
                Audio production tools for producers who want their tools to disappear into the
                workflow.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <span className="eyebrow">Products & Research</span>
              <Link href="/products" className="hover:text-[color:var(--foreground)] transition-colors">
                All products
              </Link>
              <Link href="/products/smart-sample-manager" className="hover:text-[color:var(--foreground)] transition-colors">
                SLO (Sample Library Optimiser)
              </Link>
              <Link href="/products/submit" className="hover:text-[color:var(--foreground)] transition-colors">
                Submit (Document Prep)
              </Link>
              <Link href="/technology" className="hover:text-[color:var(--foreground)] transition-colors">
                Technology
              </Link>
              <Link href="/learn" className="hover:text-[color:var(--foreground)] transition-colors">
                Learn
              </Link>
              <Link href="/pricing" className="hover:text-[color:var(--foreground)] transition-colors">
                Pricing
              </Link>
              <Link href="/support" className="hover:text-[color:var(--foreground)] transition-colors">
                Support
              </Link>
            </div>
            <div className="flex flex-col gap-2">
              <span className="eyebrow">Legal</span>
              <Link href="/privacy" className="hover:text-[color:var(--foreground)] transition-colors">
                Privacy
              </Link>
              <Link href="/terms" className="hover:text-[color:var(--foreground)] transition-colors">
                Terms
              </Link>
              <Link href="/eula" className="hover:text-[color:var(--foreground)] transition-colors">
                EULA
              </Link>
              <Link href="/refund-policy" className="hover:text-[color:var(--foreground)] transition-colors">
                Refund Policy
              </Link>
            </div>
          </div>
          <div
            className="border-t px-6 py-6 mx-auto flex flex-wrap items-center justify-between gap-4 text-xs"
            style={{ maxWidth: "var(--content-width)", borderColor: "var(--border)", color: "var(--muted-dim)" }}
          >
            <span>&copy; {new Date().getFullYear()} NITE DSP</span>
            <a href="mailto:nitedsp@outlook.com" className="hover:text-[color:var(--foreground)] transition-colors">
              nitedsp@outlook.com
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
