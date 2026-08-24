import type { Metadata } from "next";
import { BuyCard } from "./BuyCard";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Smart Sample Manager pricing — one-time purchase, perpetual license.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return (
    <>
      <section className="section pricing-hero">
        <div className="site-container">
          <span className="eyebrow">Pricing</span>
          <h1 className="section-title mt-4">One price. Yours to keep.</h1>
          <p className="body-large mt-6">
            A single purchase for Smart Sample Manager. A perpetual licence, with no subscription
            and free updates within the version.
          </p>
        </div>
      </section>

      <section className="section-rule">
        <div className="site-container pricing-layout py-12 sm:py-20">
          <div className="pricing-notes">
            <span className="eyebrow">What is included</span>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight">The complete current toolset.</h2>
            <ul className="feature-list mt-7">
              <li>Perpetual license after one purchase</li>
              <li>Up to three active machine activations</li>
              <li>macOS formats: VST3, AU, and Standalone</li>
              <li>Free updates within the 1.x version line</li>
            </ul>
            <p className="mt-8 text-sm" style={{ color: "var(--muted-dim)" }}>
              A separate £5 introductory catalog price exists for controlled testing, but it is
              not the active offer and does not transition automatically.
            </p>
          </div>

          <div className="purchase-panel">
            {/* Copper here marks commercial intent (the buy decision), not status. */}
            <span className="eyebrow" style={{ color: "var(--accent)" }}>Current one-time price</span>
            <h2 className="mt-5 text-xl font-semibold">Smart Sample Manager</h2>
            <div className="mt-7 flex items-baseline gap-3">
              <span className="text-5xl font-semibold tracking-tight">£10</span>
              <span className="text-sm" style={{ color: "var(--muted-dim)" }}>one-time</span>
            </div>
            <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
              The active offer is a single £10 purchase. There is no automatic recurring charge or
              automatic £5-to-£10 transition.
            </p>
            <BuyCard />
          </div>
        </div>
      </section>
    </>
  );
}
