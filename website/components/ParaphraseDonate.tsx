"use client";

// Stripe Payment Link with ?prefilled_amount=<pence> for one-click tier selection.
// Replace STRIPE_PAYMENT_LINK with the URL from your Stripe dashboard
// (Payment Links → your "pay what you like" link).
const STRIPE_PAYMENT_LINK = "https://buy.stripe.com/test_7sYbJ22OKbOofSt73d38400";

const TIERS = [
  { label: "£1", pence: 100, subtitle: "Just because" },
  { label: "£3", pence: 300, subtitle: "Fair trade" },
  { label: "£10", pence: 1000, subtitle: "Thanks a lot" },
];

export function ParaphraseDonate() {
  return (
    <div className="flex flex-wrap gap-3">
      {TIERS.map((tier) => (
        <a
          key={tier.pence}
          href={`${STRIPE_PAYMENT_LINK}?prefilled_amount=${tier.pence}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex flex-col items-center gap-0.5 rounded-md border border-border-strong/60 px-5 py-3 transition hover:border-brand-violet hover:bg-brand-violet/5 no-underline"
        >
          <span className="text-base font-semibold text-foreground">{tier.label}</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-dim">
            {tier.subtitle}
          </span>
        </a>
      ))}
    </div>
  );
}
