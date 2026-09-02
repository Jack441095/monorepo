import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
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
          // EMBER surface.base / text.primary / text.secondary, mirrors
          // globals.css tokens. Literal hexes required: ImageResponse renders
          // outside the CSS layer.
          // Palette B background & typography tokens
          background: "#070A12",
          color: "#F5F7FB",
          fontFamily: "system-ui, sans-serif",
          padding: "80px",
        }}
      >
        <div style={{ display: "flex", fontSize: 28, letterSpacing: 4, color: "#A7B0C0" }}>
          NITE DSP
        </div>
        <div style={{ display: "flex", fontSize: 72, fontWeight: 700, marginTop: 24 }}>
          SLO
        </div>
        <div style={{ display: "flex", fontSize: 32, color: "#397BFF", marginTop: 24 }}>
          Sample Library Optimiser
        </div>
      </div>
    ),
    size
  );
}
