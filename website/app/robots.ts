import type { MetadataRoute } from "next";

const BASE_URL = "https://nitedsp.co.uk";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Account pages require auth and carry no public SEO value --
      // excluding them keeps crawlers off session-gated routes.
      disallow: ["/account", "/auth/"],
    },
    sitemap: `${BASE_URL}/sitemap.xml`,
  };
}
