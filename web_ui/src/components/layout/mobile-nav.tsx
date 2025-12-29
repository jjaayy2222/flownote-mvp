// web_ui/src/components/layout/mobile-nav.tsx

'use client';

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, LayoutDashboard, Network, BarChart3, Settings, Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

export function MobileNav() {
  const [open, setOpen] = React.useState(false);
  const pathname = usePathname();

  return (
    <div className="md:hidden flex items-center p-4 border-b bg-white sticky top-0 z-50">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="outline" size="icon" className="mr-4">
            <Menu className="h-5 w-5" />
            <span className="sr-only">Toggle Menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="pr-0">
          <SheetHeader>
            <SheetTitle className="text-left px-2">FlowNote</SheetTitle>
          </SheetHeader>
          <div className="space-y-4 py-4">
             <div className="px-3 py-2">
              <div className="space-y-1">
                <Button variant={pathname === "/" ? "secondary" : "ghost"} className="w-full justify-start" onClick={() => setOpen(false)} asChild>
                  <Link href="/">
                    <LayoutDashboard className="mr-2 h-4 w-4" />
                    Dashboard
                  </Link>
                </Button>
                <Button variant={pathname === "/graph" ? "secondary" : "ghost"} className="w-full justify-start" onClick={() => setOpen(false)} asChild>
                  <Link href="/graph">
                    <Network className="mr-2 h-4 w-4" />
                    Graph View
                  </Link>
                </Button>
                <Button variant={pathname === "/stats" ? "secondary" : "ghost"} className="w-full justify-start" onClick={() => setOpen(false)} asChild>
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
          </div>
        </SheetContent>
      </Sheet>
      <div className="font-semibold text-lg">FlowNote Dashboard</div>
    </div>
  );
}
