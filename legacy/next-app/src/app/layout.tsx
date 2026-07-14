import type { Metadata } from "next";
import Script from "next/script";
import { PwaRegister } from "@/components/pwa-register";
import "./globals.css";

export const metadata: Metadata = {
  title: "Family App",
  description: "Gezinsapp voor huis, financien, boodschappen en Home Assistant.",
  manifest: "/manifest.webmanifest",
  applicationName: "Family App",
  appleWebApp: {
    capable: true,
    title: "Family",
    statusBarStyle: "default",
  },
  formatDetection: {
    telephone: true,
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="nl" suppressHydrationWarning>
      <body>
        {children}
        <PwaRegister />
        <Script
          id="theme-preference"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `try{var p=localStorage.getItem("family-app-theme");if(p!=="dark"&&p!=="light"&&p!=="system"){p="system"}var t=p==="system"?(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):p;document.documentElement.dataset.themePreference=p;document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t}catch(e){}`,
          }}
        />
      </body>
    </html>
  );
}
