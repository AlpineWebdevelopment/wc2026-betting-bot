import type { MetadataRoute } from "next";

// Tell every well-behaved crawler to stay out of the entire site.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: "/",
    },
  };
}
