import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Products",
  description: "Audio production tools by NITE DSP.",
  alternates: { canonical: "/products" },
};

export default function ProductsPage() {
  return (
    <>
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Products</span>
          <h1 className="section-title mt-4">Tools for finding the next idea.</h1>
          <p className="body-large mt-6">
            NITE DSP makes focused audio tools for practical production work. Each product has a
            clear job and stays out of the way when the music is moving.
          </p>
        </div>
      </section>

      <section className="section-rule">
        <div className="site-container py-12 sm:py-20">
          <Link href="/products/smart-sample-manager" className="support-card block max-w-3xl">
            <span className="eyebrow" style={{ color: "var(--accent-signal)" }}>Available now</span>
            <h2 className="mt-5 text-3xl font-semibold tracking-tight">SLO</h2>
            <p className="mt-2 text-sm" style={{ color: "var(--muted-dim)" }}>Smart Sample Manager</p>
            <p className="mt-6 max-w-xl leading-relaxed" style={{ color: "var(--muted)" }}>
              A macOS sample browser that helps you search, audition, compare, and organise the
              sounds already in your library.
            </p>
            <span className="text-link mt-8">Explore SLO <span aria-hidden="true">→</span></span>
          </Link>
        </div>
      </section>
    </>
  );
}
