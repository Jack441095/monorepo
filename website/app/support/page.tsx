import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";

export const metadata: Metadata = pageMetadata({
  title: "Support",
  description: "Support for NITE Submit, SLO, and NITE DSP products.",
  path: "/support",
});

const LINKS = [
  {
    title: "Getting Started",
    body: "Install, activate, and scan your first library in a few minutes.",
    href: "/learn/smart-sample-manager/getting-started",
  },
  {
    title: "Installation",
    body: "Plugin formats and directory locations for AU, VST3, and Standalone builds.",
    href: "/learn/smart-sample-manager/installation",
  },
  {
    title: "Troubleshooting",
    body: "Fixes for common problems, indexing issues, plugin loading, or license errors.",
    href: "/learn/smart-sample-manager/troubleshooting",
  },
  {
    title: "FAQ",
    body: "Frequently asked questions about the classification engine and audio analysis.",
    href: "/learn/smart-sample-manager/faq",
  },
];

export default function SupportPage() {
  return (
    <>
      {/* Support Hero */}
      <section className="section support-hero">
        <div className="site-container">
          <span className="eyebrow">Support Center</span>
          <h1 className="section-title mt-4 text-foreground">Get back to making music.</h1>
          <p className="body-large mt-6">
            Explore product guides or contact us directly. NITE Submit beta users should include their macOS version, app version, and a redacted description of the PDF workflow.
          </p>

          <div className="support-grid mt-12">
            {LINKS.map((item) => (
              <Link key={item.href} href={item.href} className="support-card flex flex-col justify-between">
                <div>
                  <span className="text-[10px] font-mono tracking-wider text-brand-blue-bright uppercase">READ DOCUMENTATION</span>
                  <h2 className="mt-5 font-semibold text-foreground text-lg">{item.title}</h2>
                  <p className="mt-3 text-sm text-muted">
                    {item.body}
                  </p>
                </div>
                <span className="text-link mt-8">View guide <span aria-hidden="true">&rarr;</span></span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Support Contact */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container text-center" style={{ maxWidth: "42rem" }}>
          <h2 className="text-2xl font-bold text-foreground">Still stuck?</h2>
          <p className="mt-4 text-sm text-muted leading-relaxed">
            Email us directly. Please never attach an unredacted assignment or private document. Include your macOS version, product/version, and a brief description of the issue.
          </p>
          <a href="mailto:nitedsp@outlook.com" className="btn-primary mt-8 inline-block font-mono">
            nitedsp@outlook.com
          </a>
        </div>
      </section>
    </>
  );
}
