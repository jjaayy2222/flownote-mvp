import { Sidebar } from "@/components/layout/sidebar";
import { MobileNav } from "@/components/layout/mobile-nav";

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <Sidebar className="hidden md:flex" />
      <div className="flex flex-col min-h-screen md:pl-64 transition-all duration-300 ease-in-out">
        <MobileNav />
        <main className="flex-1 p-4 md:p-8 pt-6">
          {children}
        </main>
      </div>
    </>
  );
}
