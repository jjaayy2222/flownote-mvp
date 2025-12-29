// web_ui/src/config/navigation.ts

import { LayoutDashboard, Network, BarChart3, Settings, Github } from "lucide-react";

export const mainNavItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/graph", label: "Graph View", icon: Network },
  { href: "/stats", label: "Statistics", icon: BarChart3 },
];

export const settingsItems = [
  { href: "/preferences", label: "Preferences", icon: Settings, external: false },
  { href: "https://github.com/jjaayy2222/flownote-mvp", label: "GitHub", icon: Github, external: true },
];
