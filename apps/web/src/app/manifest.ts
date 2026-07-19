import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Deep-Foundry",
    short_name: "Deep-Foundry",
    description:
      "Persistent AI coworkers with memory and human-controlled permissions.",
    start_url: "/home",
    display: "standalone",
    background_color: "#131210",
    theme_color: "#1d1b17",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icon-512-maskable.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
