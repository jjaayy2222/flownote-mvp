// web_ui/src/app/layout.tsx 

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { MobileNav } from "@/components/layout/mobile-nav";
import { Toaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"),
  title: {
    default: "FlowNote - AI Knowledge System",
    template: "%s | FlowNote",
  },
  description: "AI-powered Knowledge Management System based on PARA method. Automate your second brain.",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-50`}
      >
        <Sidebar className="hidden md:flex" />
        <div className="flex flex-col min-h-screen md:pl-64 transition-all duration-300 ease-in-out">
          <MobileNav />
          <main className="flex-1 p-4 md:p-8 pt-6">
            {children}
          </main>
        </div>
        <Toaster />
      </body>
    </html>
  );
}

