import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { ToastProvider } from "@/components/ui";

import "./globals.css";
import "./care.css";
import "./intro.css";
import { AppTour } from "@/components/app-tour";
import { AppIntro } from "@/components/app-intro";

export const metadata: Metadata = {
  title: "Niyamit Care Bridge",
  description: "Diabetes follow-up coordination for clinics: worklists, verified plans, patient replies in Telugu, Hindi and English.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg" },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0F2A44" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppIntro />
        <AppTour />
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
