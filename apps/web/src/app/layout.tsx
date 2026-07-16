import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppShell } from "@/components/app-shell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Deep-Foundry",
  description: "Persistent AI coworkers with memory and human-controlled permissions.",
};

// Runs synchronously before first paint: reads the saved preference and sets
// the `.dark` class so the correct theme is on screen immediately — no flash
// of the default (light) theme for users who chose dark. Kept in sync with
// lib/theme.ts (same key, same resolution). Unset preference → light.
const THEME_INIT_SCRIPT = `!function(){try{var k="deep-foundry.theme",p=localStorage.getItem(k),d=p==="dark"||(p==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d)}catch(e){}}()`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
