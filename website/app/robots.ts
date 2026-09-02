import type { MetadataRoute } from "next";

// www, not the bare apex, see sitemap.ts's comment.
const BASE_URL = "https://www.nitedsp.co.uk";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Account pages require auth and carry no public SEO value --
      // excluding them keeps crawlers off session-gated routes.
      // /portfolio is an unlisted, employer-facing private page (no nav
      // link, no sitemap entry) -- kept out of the index as a second layer
      // alongside its own page-level noindex/nofollow metadata.
      disallow: ["/account", "/auth/", "/portfolio"],
    },
    sitemap: `${BASE_URL}/sitemap.xml`,
  };
}
