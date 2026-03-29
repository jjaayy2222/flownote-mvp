import type { Metadata } from 'next';

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
    <div className="flex flex-col min-h-screen admin-container">
      {/* Placeholder for Admin Navbar and Sidebar */}
      <main className="flex-1 p-4 md:p-8">
        {children}
      </main>
    </div>
  );
}
