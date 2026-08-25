// Central commercial-maturity switch (docs/NITE_DSP_CONVERSION_COMMERCIAL_UX_V1.md §1).
// Launch procedure: set NEXT_PUBLIC_CHECKOUT_LIVE=1 at build time once Paddle
// prices are approved and the backend reports 200 from /commerce/checkout.
// Every CtaButton asking for BUY_LIVE then renders the buy flow; until then
// they fall back to BETA_REQUEST so no surface ever shows a dead Buy button.
export const CHECKOUT_LIVE =
  process.env.NEXT_PUBLIC_CHECKOUT_LIVE === "1";
