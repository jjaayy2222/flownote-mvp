// web_ui/src/components/layout/nav-item.tsx

"use client";

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

  return (
    <Button
      variant={isActive ? "secondary" : "ghost"}
      className="w-full justify-start"
      asChild={!external}
      onClick={onClick}
    >
      {external ? (
        <a href={href} target="_blank" rel="noreferrer">
          {content}
        </a>
      ) : (
        <Link href={href}>{content}</Link>
      )}
    </Button>
  );
}
