import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          // EMBER surface.base / text.primary — mirrors globals.css tokens.
          // Literal hexes required: ImageResponse renders outside the CSS layer.
          background: "#0c0b09",
          borderRadius: 6,
          color: "#ede8e0",
          fontSize: 20,
          fontWeight: 700,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        N
      </div>
    ),
    size
  );
}
