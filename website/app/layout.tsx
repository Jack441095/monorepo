import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
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
// 5.6). Hardcoded here deliberately -- unlike NEXT_PUBLIC_NITE_DSP_API_URL
// (a functional fetch target that must never point at the wrong
// environment), metadataBase/canonical/OG URLs are pure metadata about the
// site's real-world identity, safe to state directly regardless of which
// environment is currently serving the page.
export const metadata: Metadata = {
  metadataBase: new URL("https://nitedsp.co.uk"),
  title: {
    default: "NITE DSP",
    template: "%s | NITE DSP",
  },
  description: "Audio production tools by NITE DSP.",
  openGraph: {
    title: "NITE DSP",
    description: "Audio production tools by NITE DSP.",
    url: "https://nitedsp.co.uk",
    siteName: "NITE DSP",
    type: "website",
  },
};

const NAV_LINKS = [
  { href: "/products/smart-sample-manager", label: "Smart Sample Manager" },
  { href: "/pricing", label: "Pricing" },
  { href: "/support", label: "Support" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col" style={{ background: "var(--background)", color: "var(--foreground)" }}>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <header className="border-b sticky top-0 z-40 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--background)]/80" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <nav
            className="mx-auto flex items-center justify-between px-6 py-4"
            style={{ maxWidth: "var(--content-width)" }}
            aria-label="Primary"
          >
            <Link href="/" className="font-semibold tracking-tight text-lg">
              NITE DSP
            </Link>
            <div className="hidden sm:flex items-center gap-8 text-sm" style={{ color: "var(--muted)" }}>
              {NAV_LINKS.map((link) => (
                <Link key={link.href} href={link.href} className="hover:text-[color:var(--foreground)] transition-colors">
                  {link.label}
                </Link>
              ))}
            </div>
            <Link href="/account" className="btn-secondary">
              Account
            </Link>
          </nav>
        </header>

        <main id="main" className="flex-1">
          {children}
        </main>

        <footer className="border-t mt-16" style={{ borderColor: "var(--border)" }}>
          <div
            className="mx-auto px-6 py-12 grid gap-10 sm:grid-cols-3 text-sm"
            style={{ maxWidth: "var(--content-width)", color: "var(--muted)" }}
          >
            <div>
              <div className="font-semibold text-[color:var(--foreground)]">NITE DSP</div>
              <p className="mt-2 text-xs" style={{ color: "var(--muted-dim)" }}>
                Audio production tools for producers who want their tools to disappear into the
                workflow.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <span className="eyebrow">Product</span>
              <Link href="/products/smart-sample-manager" className="hover:text-[color:var(--foreground)] transition-colors">
                Smart Sample Manager
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
