import type { Metadata } from "next";
import Link from "next/link";
import { BetaRequestForm } from "@/components/BetaRequestForm";

export const metadata: Metadata = {
  title: "Beta Access",
  description: "Request access to the NITE Submit closed beta, or ask to be notified when SLO and KENN open up.",
  alternates: { canonical: "/beta" },
};

const STEPS = [
  ["01", "Request", "Tell us who you are and what you'd like to do. Requests go to our team by email — nothing is uploaded."],
  ["02", "Invitation", "We review requests manually and send an invitation with download instructions for the signed macOS build."],
  ["03", "Feedback", "Beta users talk directly to nitedsp@outlook.com. Your feedback shapes what ships."],
  ["04", "Future purchase", "When the £2.99 perpetual licence experiment opens, beta participants hear first."],
];

export default function BetaPage() {
  return (
    <>
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Closed Beta</span>
          <h1 className="section-title mt-4 text-foreground">Try NITE software early.</h1>
          <p className="body-large mt-6">
            NITE Submit is in a free invitation-only closed beta. SLO remains separately gated, and
            KENN is in development. Request access, or ask us to notify you as products mature.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
          <BetaRequestForm />
          <div>
            <span className="eyebrow">How it works</span>
            <ol className="mt-6 flex flex-col gap-6">
              {STEPS.map(([n, title, body]) => (
                <li key={n} className="flex gap-4">
                  <span className="u-data" style={{ color: "var(--brand-blue-bright)" }}>{n}</span>
                  <div>
                    <h2 className="text-sm font-semibold text-foreground">{title}</h2>
                    <p className="mt-1 text-xs leading-relaxed text-muted">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-8 text-xs text-muted-dim leading-relaxed">
              Questions first?{" "}
              <Link href="/support" className="text-link">
                Visit support
              </Link>{" "}
              or read{" "}
              <Link href="/trust" className="text-link">
                how we handle your data
              </Link>
              .
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
