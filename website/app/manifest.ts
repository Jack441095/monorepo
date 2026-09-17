import type { MetadataRoute } from "next";

// Gives the site a real installed/tab identity instead of the browser's
// default. Colours mirror the Palette C tokens the site actually ships with
// (data-theme="c" in app/layout.tsx); literal hexes are required here because
// a manifest is served as JSON, outside the CSS layer.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "NITE DSP",
    short_name: "NITE DSP",
    description: "Local-first macOS tools for producers and students.",
    start_url: "/",
    display: "standalone",
    background_color: "#090B10",
    theme_color: "#090B10",
    icons: [
      { src: "/icon", sizes: "32x32", type: "image/png" },
      { src: "/favicon.ico", sizes: "any", type: "image/x-icon" },
    ],
  };
}
