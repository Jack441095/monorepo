// Public Payment Links change state independently of the website deploy. Keep
// their URLs in Vercel so deactivated dashboard links cannot ship in the bundle.
export const STRIPE_MIXING_DEPOSIT_LINK = "";
export const STRIPE_MASTERING_DEPOSIT_LINK = "";
export const STRIPE_SLO_LINK = process.env.NEXT_PUBLIC_STRIPE_SLO_LINK ?? "";
export const STRIPE_SUBMIT_LINK = process.env.NEXT_PUBLIC_STRIPE_SUBMIT_LINK ?? "";

export function isHostedStripeCheckoutUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      url.pathname !== "/" &&
      (url.hostname === "buy.stripe.com" || url.hostname === "checkout.stripe.com")
    );
  } catch {
    return false;
  }
}

// Checkout approvals follow docs/STRIPE_COMMERCE.md. Website flags and the
// backend gate must agree before launch; Payment Links have a separate state.
// Every CtaButton asking for BUY_LIVE then renders the buy flow; until then
// they fall back to BETA_REQUEST so no surface ever shows a dead Buy button.
export const STRIPE_MODE = process.env.NEXT_PUBLIC_STRIPE_MODE;
export const LEGAL_REVIEW_APPROVED =
  process.env.NEXT_PUBLIC_LEGAL_REVIEW_APPROVED === "1";
export const RELEASE_READY =
  process.env.NEXT_PUBLIC_RELEASE_READY === "1";

// Sandbox remains available for controlled rehearsals. A real-money button is
// impossible unless checkout, legal approval, and a public release are all
// explicitly enabled in the production build.
export const CHECKOUT_LIVE =
  process.env.NEXT_PUBLIC_CHECKOUT_LIVE === "1" &&
  (STRIPE_MODE === "test" ||
    (STRIPE_MODE === "live" && LEGAL_REVIEW_APPROVED && RELEASE_READY));

export const PUBLIC_CHECKOUT_LIVE =
  CHECKOUT_LIVE &&
  STRIPE_MODE === "live" &&
  isHostedStripeCheckoutUrl(STRIPE_SUBMIT_LINK) &&
  isHostedStripeCheckoutUrl(STRIPE_SLO_LINK);
