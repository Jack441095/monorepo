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
          // EMBER surface.base / text.primary / text.secondary — mirrors
          // globals.css tokens. Literal hexes required: ImageResponse renders
          // outside the CSS layer.
          background: "#0c0b09",
          color: "#ede8e0",
          fontFamily: "system-ui, sans-serif",
          padding: "80px",
        }}
      >
        <div style={{ display: "flex", fontSize: 28, letterSpacing: 4, color: "#a39b8f" }}>
          NITE DSP
        </div>
        <div style={{ display: "flex", fontSize: 72, fontWeight: 700, marginTop: 24 }}>
          Smart Sample Manager
        </div>
        <div style={{ display: "flex", fontSize: 32, color: "#e89b3c", marginTop: 24 }}>
          Your samples. Actually organised.
        </div>
      </div>
    ),
    size
  );
}
