"use client";

const TIERS = [
  { label: "£1", subtitle: "Just because", url: "https://buy.stripe.com/5kQcN6fCB0NyaB3epz5sA01" },
  { label: "£3", subtitle: "Fair trade",   url: "https://buy.stripe.com/5kQeVefCBgMweRj3KV5sA02" },
  { label: "£10", subtitle: "Thanks a lot", url: "https://buy.stripe.com/3cIbJ26212VGgZrepz5sA03" },
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
