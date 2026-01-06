// web_ui/src/components/layout/mobile-nav.tsx

'use client';

import * as React from "react";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { NavItem } from "./nav-item";
import { mainNavItems, settingsItems } from "@/config/navigation";

export function MobileNav() {
  const [open, setOpen] = React.useState(false);

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
                {mainNavItems.map(item => (
                  <NavItem key={item.href} {...item} onClick={() => setOpen(false)} />
                ))}
              </div>
            </div>
             <div className="px-3 py-2">
               <h2 className="mb-2 px-4 text-lg font-semibold tracking-tight">
                Settings
              </h2>
              <div className="space-y-1">
                {settingsItems.map(item => (
                  <NavItem key={item.href} {...item} onClick={() => setOpen(false)} />
                ))}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>
      <div className="font-semibold text-lg">FlowNote Dashboard</div>
    </div>
  );
}
