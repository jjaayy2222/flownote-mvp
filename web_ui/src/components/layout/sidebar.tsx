// web_ui/src/components/layout/sidebar.tsx

import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { NavItem } from "./nav-item";
import { mainNavItems, settingsItems } from "@/config/navigation";

export function Sidebar({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...props} className={cn("hidden md:block w-64 fixed left-0 top-0 h-screen border-r bg-slate-50/50", className)}>
      <ScrollArea className="h-full py-4">
        <div className="px-3 py-2">
          <h2 className="mb-2 px-4 text-lg font-semibold tracking-tight">FlowNote</h2>
          <div className="space-y-1">
            {mainNavItems.map(item => (
              <NavItem key={item.href} {...item} />
            ))}
          </div>
        </div>
        <div className="px-3 py-2">
          <h2 className="mb-2 px-4 text-lg font-semibold tracking-tight">Settings</h2>
          <div className="space-y-1">
            {settingsItems.map(item => (
              <NavItem key={item.href} {...item} />
            ))}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

