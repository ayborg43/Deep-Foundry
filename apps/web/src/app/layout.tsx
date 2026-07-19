import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";

import { AppShell } from "@/components/app-shell";
import { PwaRegister } from "@/components/pwa-register";

const hankenGrotesk = Hanken_Grotesk({
  variable: "--font-hanken-grotesk",
  subsets: ["latin"],
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Deep-Foundry",
  description: "Persistent AI coworkers with memory and human-controlled permissions.",
  applicationName: "Deep-Foundry",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Deep-Foundry",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f4f0" },
    { media: "(prefers-color-scheme: dark)", color: "#131210" },
  ],
};

// Runs synchronously before first paint: (1) sets the `.dark` class so the
// correct theme is on screen immediately — no flash of the default (light)
// theme for users who chose dark; (2) marks `.js` so scroll-reveal elements
// start hidden only when JS is present (no-JS / headless → content stays
// visible). Kept in sync with lib/theme.ts (same key, same resolution).
const THEME_INIT_SCRIPT = `!function(){try{document.documentElement.classList.add("js");var k="deep-foundry.theme",p=localStorage.getItem(k),d=p==="dark"||(p==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d)}catch(e){}}()`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${hankenGrotesk.variable} ${jetBrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <PwaRegister />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
