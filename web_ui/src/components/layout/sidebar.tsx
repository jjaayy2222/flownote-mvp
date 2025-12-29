// web_ui/src/components/layout/sidebar.tsx

'use client';

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { LayoutDashboard, Network, BarChart3, Settings, Github } from "lucide-react";

// interface SidebarProps extends React.HTMLAttributes<HTMLDivElement> {
//   // Add specific props if needed, currently empty is fine for extension
// }

export function Sidebar({ className }: React.HTMLAttributes<HTMLDivElement>) {
  const pathname = usePathname();

  return (
    <div className={cn("hidden md:block w-64 fixed left-0 top-0 h-screen border-r bg-slate-50/50", className)}>
      <ScrollArea className="h-full py-4">
        <div className="px-3 py-2">
          <h2 className="mb-2 px-4 text-lg font-semibold tracking-tight">
            FlowNote
          </h2>
          <div className="space-y-1">
            <Button variant={pathname === "/" ? "secondary" : "ghost"} className="w-full justify-start" asChild>
              <Link href="/">
                <LayoutDashboard className="mr-2 h-4 w-4" />
                Dashboard
              </Link>
            </Button>
            <Button variant={pathname === "/graph" ? "secondary" : "ghost"} className="w-full justify-start" asChild>
              <Link href="/graph">
                <Network className="mr-2 h-4 w-4" />
                Graph View
              </Link>
            </Button>
            <Button variant={pathname === "/stats" ? "secondary" : "ghost"} className="w-full justify-start" asChild>
              <Link href="/stats">
                <BarChart3 className="mr-2 h-4 w-4" />
                Statistics
              </Link>
            </Button>
          </div>
        </div>
        <div className="px-3 py-2">
          <h2 className="mb-2 px-4 text-lg font-semibold tracking-tight">
            Settings
          </h2>
          <div className="space-y-1">
            <Button variant="ghost" className="w-full justify-start">
              <Settings className="mr-2 h-4 w-4" />
              Preferences
            </Button>
            <Button variant="ghost" className="w-full justify-start">
              <Github className="mr-2 h-4 w-4" />
              GitHub
            </Button>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

