import { ImageResponse } from "next/og";

/* Shared Open Graph card.
 *
 * Every page used to inherit the single root card, which read "SLO / Sample
 * Library Optimiser" — so sharing the homepage, Submit, KENN or a legal page
 * all produced an SLO advert. Each product segment now owns its own card and
 * the root one carries brand-level messaging.
 *
 * Literal hexes throughout: ImageResponse renders via satori, outside the CSS
 * layer, so the globals.css custom properties are not available here. These
 * mirror the Palette C tokens the site ships with. Every element also carries
 * an explicit `display`, which satori requires. */

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_CONTENT_TYPE = "image/png";

const BACKGROUND = "#090B10";
const TEXT_PRIMARY = "#F5F7FB";
const TEXT_MUTED = "#9098A6";

/** Product-family accents, matching the eyebrow colours used on the site. */
export const OG_ACCENT = {
  brand: "#56A8FF",
  workflow: "#56A8FF",
  files: "#10B981",
  audio: "#9277F2",
} as const;

type OgCardInput = {
  /** Small letterspaced line above the title. */
  eyebrow: string;
  /** The large headline — keep it short, it renders at 84px. */
  title: string;
  /** Accent-coloured line beneath the title. */
  subtitle: string;
  accent: string;
};

export function ogCard({ eyebrow, title, subtitle, accent }: OgCardInput) {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "center",
          background: BACKGROUND,
          color: TEXT_PRIMARY,
          fontFamily: "system-ui, sans-serif",
          padding: "80px",
        }}
      >
        <div style={{ display: "flex", fontSize: 28, letterSpacing: 4, color: TEXT_MUTED }}>
          {eyebrow}
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 84,
            fontWeight: 700,
            marginTop: 24,
            letterSpacing: -2,
            lineHeight: 1.05,
          }}
        >
          {title}
        </div>
        <div style={{ display: "flex", fontSize: 32, color: accent, marginTop: 24 }}>
          {subtitle}
        </div>
        {/* Accent rule, anchoring the card to the family colour. */}
        <div
          style={{
            display: "flex",
            width: 160,
            height: 6,
            marginTop: 48,
            background: accent,
            borderRadius: 3,
          }}
        />
      </div>
    ),
    OG_SIZE,
  );
}
