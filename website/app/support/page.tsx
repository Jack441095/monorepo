import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Support",
  description: "Getting started, installation, activation, troubleshooting, and contact for Smart Sample Manager.",
  alternates: { canonical: "/support" },
};

const LINKS = [
  {
    title: "Getting Started",
    body: "Install, activate, and index your first library in a few minutes.",
    href: "/learn/smart-sample-manager/getting-started",
  },
  {
    title: "Installation",
    body: "Where VST3, AU, and Standalone install, and how to load the plugin in your DAW.",
    href: "/learn/smart-sample-manager/installation",
  },
  {
    title: "Troubleshooting",
    body: "Fixes for the most common issues -- plugin not appearing, activation, scanning, previews.",
    href: "/learn/smart-sample-manager/troubleshooting",
  },
  {
    title: "FAQ",
    body: "Answers to common questions about how Smart Sample Manager works.",
    href: "/learn/smart-sample-manager/faq",
  },
];

export default function SupportPage() {
  return (
    <>
      <section className="section">
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <span className="eyebrow">Support</span>
          <h1 className="mt-3 text-3xl sm:text-5xl font-semibold tracking-tight text-balance">
            How can we help?
          </h1>
          <p className="mt-5 text-lg max-w-2xl" style={{ color: "var(--muted)" }}>
            Guides for installing, activating, and using Smart Sample Manager -- and a direct
            line to NITE DSP if you&apos;re still stuck.
          </p>

          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {LINKS.map((item) => (
              <Link key={item.href} href={item.href} className="surface-card p-6 block">
                <h2 className="font-medium">{item.title}</h2>
                <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
                  {item.body}
                </p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6 text-center" style={{ maxWidth: "42rem" }}>
          <h2 className="text-xl font-semibold tracking-tight">Still stuck?</h2>
          <p className="mt-3 text-sm" style={{ color: "var(--muted)" }}>
            Email us directly with your Smart Sample Manager version, macOS version, DAW (if
            relevant), and what you were trying to do -- we&apos;ll help you sort it out.
          </p>
          <a href="mailto:nitedsp@outlook.com" className="btn-primary mt-6 inline-block">
            nitedsp@outlook.com
          </a>
        </div>
      </section>
    </>
  );
}
