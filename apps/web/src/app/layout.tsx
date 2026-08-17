import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Mundial 2030 Sirius Engine",
  description: "Escenario experimental, trazable y reproducible del Mundial 2030"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className={`${sans.variable} ${mono.variable}`}>{children}</body>
    </html>
  );
}
