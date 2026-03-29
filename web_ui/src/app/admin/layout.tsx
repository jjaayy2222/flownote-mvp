// web_ui/src/app/admin/layout.tsx

import { Geist, Geist_Mono } from "next/font/google";
import "@/app/globals.css"; // Ensure admin uses the global CSS (Tailwind)
import type { Metadata } from 'next';

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Flownote Admin",
  description: "Admin Dashboard for Flownote MVP",
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-50`}>
        {/* Placeholder for Admin Navbar and Sidebar */}
        <div className="flex flex-col min-h-screen">
          <main className="flex-1 p-4 md:p-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
