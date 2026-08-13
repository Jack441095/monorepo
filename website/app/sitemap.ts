import type { MetadataRoute } from "next";

const BASE_URL = "https://nitedsp.co.uk";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = ["", "/products/smart-sample-manager", "/pricing", "/support", "/privacy", "/terms", "/eula", "/refund-policy"];
  return routes.map((route) => ({
    url: `${BASE_URL}${route}`,
    lastModified: new Date(),
  }));
}
