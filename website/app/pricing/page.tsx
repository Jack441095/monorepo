import type { Metadata } from "next";
import { BuyCard } from "./BuyCard";

export const metadata: Metadata = {
  title: "Pricing",
  description: "SLO pricing — one-time purchase, perpetual license, and fully offline.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return (
    <>
      {/* Pricing Hero */}
      <section className="section pricing-hero">
        <div className="site-container">
          <span className="eyebrow">Pricing</span>
          <h1 className="section-title mt-4 text-foreground">One price. Yours to keep.</h1>
          <p className="body-large mt-6">
            A single purchase for SLO. A perpetual licence with no recurring subscriptions, no cloud dependencies, and free updates within the version line.
          </p>
        </div>
      </section>

      {/* Pricing Layout */}
      <section className="section-rule">
        <div className="site-container pricing-layout py-12 sm:py-20">
          <div className="pricing-notes">
            <span className="eyebrow">License Terms</span>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">What is included.</h2>
            <ul className="feature-list mt-7">
              <li>Perpetual offline license after a single purchase</li>
              <li>Up to three active personal activations</li>
              <li>macOS formats: AU, VST3, and Standalone</li>
              <li>Free updates within the 1.x version line</li>
              <li>100% private: no data uploads or network requirements</li>
            </ul>
            <p className="mt-8 text-xs text-muted-dim">
              An introductory catalog price of £5 exists for controlled alpha testers but is not currently the active commercial offer.
            </p>
          </div>

          <div className="purchase-panel border border-brand-blue/30">
            <span className="eyebrow text-brand-blue-bright">Single-User Licence</span>
            <h2 className="mt-5 text-xl font-bold text-foreground">SLO</h2>
            <p className="text-xs text-muted-dim font-mono mt-0.5">Sample Library Optimiser</p>
            
            <div className="mt-7 flex items-baseline gap-2">
              <span className="text-5xl font-bold tracking-tight text-foreground">£10</span>
              <span className="text-sm text-muted-dim font-mono">one-time</span>
            </div>
            
            <p className="mt-4 text-xs leading-relaxed text-muted">
              Purchase includes Standalone app and AU/VST3 plugin builds for Intel & Apple Silicon Macs. No subscription required.
            </p>
            
            <BuyCard />
          </div>
        </div>
      </section>
    </>
  );
}
