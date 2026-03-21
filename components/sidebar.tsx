"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Separator } from "@/components/ui/separator";

/**
 * Sidebar navigation for the dashboard layout.
 *
 * Fixed-position, 220px wide, dark background with teal active indicators.
 * Uses usePathname() to highlight the currently active nav item.
 */

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: "\u{1F4CA}" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-[220px] flex-col bg-zinc-900 border-r border-zinc-800">
      {/* Brand */}
      <div className="px-5 py-6">
        <Link href="/dashboard" className="text-lg font-bold text-[#00B4D8]">
          {"\u{1F34A}"} OJ Engine
        </Link>
      </div>

      <Separator className="bg-zinc-800" />

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "border-l-2 border-[#00B4D8] bg-zinc-800 text-[#00B4D8]"
                      : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                  }`}
                >
                  <span>{item.icon}</span>
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Version */}
      <div className="px-5 py-4">
        <Separator className="mb-4 bg-zinc-800" />
        <p className="text-xs text-zinc-600">v1.0.0</p>
      </div>
    </aside>
  );
}
