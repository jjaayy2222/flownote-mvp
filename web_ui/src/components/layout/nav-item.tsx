// web_ui/src/components/layout/nav-item.tsx

"use client";

import type React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";

interface NavItemProps {
  href: string;
  label: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  external?: boolean;
  onClick?: () => void;
}

export function NavItem({ href, label, icon: Icon, external, onClick }: NavItemProps) {
  const pathname = usePathname();
  const isActive = !external && pathname === href;

  const content = (
    <>
      <Icon className="mr-2 h-4 w-4" />
      {label}
    </>
  );

  // Use asChild=true for both cases to avoid <button> inside <button> nesting issues
  // The Button component with asChild will render the child element (Link or a) directly
  // while preserving the button styles.
  return (
    <Button
      variant={isActive ? "secondary" : "ghost"}
      className="w-full justify-start"
      asChild
      onClick={onClick}
    >
      {external ? (
        <a href={href} target="_blank" rel="noreferrer noopener">
          {content}
        </a>
      ) : (
        <Link href={href}>{content}</Link>
      )}
    </Button>
  );
}
