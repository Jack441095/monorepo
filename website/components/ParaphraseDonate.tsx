"use client";

// TODO: swap test_ URLs for live payment links before launch
const TIERS = [
  { label: "£1", subtitle: "Just because", url: "https://buy.stripe.com/test_7sY3cwgGFdAk6kN6X75sA04" },
  { label: "£3", subtitle: "Fair trade",   url: "https://buy.stripe.com/test_cNiaEYdutbsc38B3KV5sA05" },
  { label: "£10", subtitle: "Thanks a lot", url: "https://buy.stripe.com/test_28E00k1LL7bWbF7bdn5sA06" },
];

export function ParaphraseDonate() {
  return (
    <div className="flex flex-wrap gap-3">
      {TIERS.map((tier) => (
        <a
          key={tier.label}
          href={tier.url}
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
