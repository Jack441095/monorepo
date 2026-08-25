import type { Metadata } from "next";
import Link from "next/link";
import { CtaButton } from "@/components/CtaButton";
import { CHECKOUT_LIVE } from "@/lib/commerce-config";

export const metadata: Metadata = {
  title: "Pricing",
  description: "NITE Submit beta and planned perpetual pricing.",
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
            NITE Submit is currently in a free closed beta. The first paid experiment will be a simple £2.99 perpetual licence with no subscription.
          </p>
        </div>
      </section>

      {/* Product Comparison */}
      <section className="section-rule">
        <div className="site-container py-12 sm:py-20">
          <span className="eyebrow">Compare</span>
          <h2 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">
            Three tools. One honest price model.
          </h2>
          <div className="mt-8 overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: "40rem", borderCollapse: "collapse" }}>
              <thead>
                <tr className="text-left u-label" style={{ color: "var(--muted-dim)" }}>
                  <th scope="col" className="py-3 pr-4 font-semibold">&nbsp;</th>
                  <th scope="col" className="py-3 pr-4 font-semibold text-foreground">Submit</th>
                  <th scope="col" className="py-3 pr-4 font-semibold text-foreground">SLO</th>
                  <th scope="col" className="py-3 pr-4 font-semibold text-foreground">KENN</th>
                </tr>
              </thead>
              <tbody style={{ color: "var(--muted)" }}>
                {[
                  ["Purpose", "Prepare the right submission", "Find the right sound", "Understand the mix"],
                  ["Status", "Closed Beta — free", "Private Beta / Research", "In development"],
                  ["Local processing", "Documents never leave your Mac", "Audio analysis runs on your machine", "Planned: local analysis"],
                  ["Account required", "No", "Activation check-in only", "—"],
                  ["Price model", "£2.99 perpetual planned · no subscription", "Pricing announced at launch", "Pricing announced at launch"],
                ].map(([label, ...cells]) => (
                  <tr key={label} style={{ borderTop: "1px solid var(--border)" }}>
                    <th scope="row" className="py-4 pr-4 text-left text-xs font-semibold text-foreground">{label}</th>
                    {cells.map((c, i) => (
                      <td key={i} className="py-4 pr-4 text-xs leading-relaxed">{c}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-6 text-xs text-muted-dim max-w-2xl">
            Thursday is internal infrastructure and is not sold. Full product details:{" "}
            <Link href="/products/submit" className="text-link">Submit</Link>,{" "}
            <Link href="/products/smart-sample-manager" className="text-link">SLO</Link>,{" "}
            <Link href="/products/kenn" className="text-link">KENN</Link>.
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
              <li>Free invitation-only closed beta</li>
              <li>Planned £2.99 perpetual licence experiment</li>
              <li>macOS 13+ Apple Silicon application</li>
              <li>No recurring subscription for V1</li>
              <li>Local PDF processing with no document upload</li>
            </ul>
            <p className="mt-8 text-xs text-muted-dim">
              Introductory pricing will be announced at launch. Private beta participants will be notified.
            </p>
          </div>

          <div className="purchase-panel border border-brand-blue/30">
            <span className="eyebrow text-brand-blue-bright">Single-User Licences</span>
            <h2 className="mt-5 text-xl font-bold text-foreground">NITE Submit</h2>
            <p className="text-xs text-muted-dim font-mono mt-0.5">Submission Preparation Intelligence</p>
            
            <div className="mt-8 space-y-6">
              {/* Planned paid experiment */}
              <div className="border-b pb-5" style={{ borderColor: "var(--border)" }}>
                <div className="flex justify-between items-baseline">
                  <span className="text-sm font-semibold text-foreground">Perpetual Licence — planned</span>
                  <span className="text-2xl font-bold text-foreground tnum">£2.99</span>
                </div>
                <p className="mt-1 text-xs text-muted leading-relaxed">
                  A low-friction paid experiment after the free closed beta. Final availability follows validation, signing, and legal gates.
                </p>
              </div>

              {/* Current beta */}
              <div className="pb-2">
                <div className="flex justify-between items-baseline">
                  <span className="text-sm font-semibold text-foreground">Closed Beta</span>
                  <span className="text-2xl font-bold text-foreground tnum">Free</span>
                </div>
                <p className="mt-1 text-xs text-muted leading-relaxed">
                  Invitation-only while real-document review, notarised distribution, and support workflows are completed.
                </p>
              </div>
            </div>
            
            <div className="mt-8 flex flex-wrap gap-3">
              {/* BUY_LIVE is fail-closed: without NEXT_PUBLIC_CHECKOUT_LIVE=1
                  this remains the honest beta-request journey. */}
              <CtaButton state="BUY_LIVE" />
              <Link href="/learn" className="btn-secondary">
                Read guides
              </Link>
            </div>

            <p className="mt-4 text-xs leading-relaxed text-muted-dim">
              NITE Submit is a local macOS app. It does not submit work for the user and cannot guarantee that generic presets match a department&apos;s rules.
            </p>
            
            <p className="mt-6 text-xs text-muted-dim">
              {CHECKOUT_LIVE
                ? "Sandbox checkout is enabled for authorised integration testing only; this is not a public launch."
                : "Checkout is not open yet. Join the beta or contact support when the paid experiment is announced."}
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
