import type { Metadata } from "next";
import Link from "next/link";
import { LEARN_PAGES } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Learn",
  description: "Guides and documentation for NITE DSP products.",
  alternates: { canonical: "/learn" },
};

export default function LearnHomePage() {
  return (
    <div className="section">
      <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
        <span className="eyebrow">Learn</span>
        <h1 className="mt-3 text-3xl sm:text-5xl font-semibold tracking-tight text-balance">
          Documentation
        </h1>
        <p className="mt-5 text-lg max-w-2xl" style={{ color: "var(--muted)" }}>
          Guides for getting the most out of NITE DSP products.
        </p>

        <div className="mt-12 surface-card p-6 max-w-xl">
          <h2 className="font-medium text-lg">Smart Sample Manager</h2>
          <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
            Installation, activation, and every workflow -- from your first library scan to
            Find Similar and the visual map.
          </p>
          <ul className="mt-4 space-y-1 text-sm">
            {LEARN_PAGES.map((p) => (
              <li key={p.slug}>
                <Link
                  href={`/learn/smart-sample-manager/${p.slug}`}
                  className="hover:text-[color:var(--foreground)] transition-colors"
                  style={{ color: "var(--muted)" }}
                >
                  {p.title}
                </Link>
              </li>
            ))}
          </ul>
          <Link href="/learn/smart-sample-manager/getting-started" className="btn-primary mt-6 inline-block">
            Start with Getting Started
          </Link>
        </div>
      </div>
    </div>
  );
}
