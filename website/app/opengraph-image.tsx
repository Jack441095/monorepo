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
          background: "#09090b",
          color: "#f4f4f5",
          fontFamily: "system-ui, sans-serif",
          padding: "80px",
        }}
      >
        <div style={{ display: "flex", fontSize: 28, letterSpacing: 4, color: "#a1a1aa" }}>
          NITE DSP
        </div>
        <div style={{ display: "flex", fontSize: 72, fontWeight: 700, marginTop: 24 }}>
          Smart Sample Manager
        </div>
        <div style={{ display: "flex", fontSize: 32, color: "#a1a1aa", marginTop: 24 }}>
          Your samples. Actually organised.
        </div>
      </div>
    ),
    size
  );
}
