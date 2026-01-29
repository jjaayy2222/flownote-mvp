// web_ui/src/config/navigation.ts

import { LayoutDashboard, Network, BarChart3, Settings, Github } from "lucide-react";

// Translation keys defined in en.json/ko.json under "navigation" namespace
export type TranslationKey = "dashboard" | "graph" | "stats" | "preferences" | "github";

export interface NavigationItem {
  href: string;
  label: TranslationKey;
  icon: React.ComponentType<{ className?: string }>;
  external?: boolean;
}

export const mainNavItems: NavigationItem[] = [
  { href: "/", label: "dashboard", icon: LayoutDashboard },
  { href: "/graph", label: "graph", icon: Network },
  { href: "/stats", label: "stats", icon: BarChart3 },
];

export const settingsItems: NavigationItem[] = [
  { href: "/preferences", label: "preferences", icon: Settings, external: false },
  { href: "https://github.com/jjaayy2222/flownote-mvp", label: "github", icon: Github, external: true },
];
