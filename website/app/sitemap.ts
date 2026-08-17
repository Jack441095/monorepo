import type { MetadataRoute } from "next";
import { LEARN_PAGES } from "@/lib/learn";

// www.nitedsp.co.uk, not the bare apex — Railway's custom domain (and this
// app's actual production deployment) is www; the apex only redirects to it
// at the DNS/registrar level (docs/IONOS_DNS_SETUP.md).
const BASE_URL = "https://www.nitedsp.co.uk";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "",
    "/products/smart-sample-manager",
    "/pricing",
    "/support",
    "/learn",
    ...LEARN_PAGES.map((p) => `/learn/smart-sample-manager/${p.slug}`),
    "/privacy",
    "/terms",
    "/eula",
    "/refund-policy",
  ];
  return routes.map((route) => ({
    url: `${BASE_URL}${route}`,
    lastModified: new Date(),
  }));
}
