"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  ListChecks,
  ScrollText,
  Gauge,
  Bell,
  Settings,
} from "lucide-react";
import { AminaLogo } from "./amina-logo";

const NAV = [
  { label: "Portfolio", href: "/dashboard", icon: LayoutDashboard },
  { label: "Clients", href: "/dashboard", icon: Users },
  { label: "Review queue", href: "#", icon: ListChecks, badge: 3 },
  { label: "Alerts", href: "#", icon: Bell, badge: 7 },
  { label: "Audit log", href: "#", icon: ScrollText },
  { label: "Cost & metrics", href: "#", icon: Gauge },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-[220px] shrink-0 flex-col border-r border-brand-deep/40 bg-brand text-white md:flex">
      <Link href="/dashboard" className="block px-5 pt-5 pb-1">
        <AminaLogo className="h-6 w-auto text-white" />
      </Link>
      <div className="px-5 pb-3 text-[10px] uppercase tracking-[0.18em] text-teal-bright">
        Drift Intelligence
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {NAV.map((item, i) => {
          const active = item.href !== "#" && pathname.startsWith(item.href) && i === 0;
          const Icon = item.icon;
          return (
            <Link
              key={item.label + i}
              href={item.href}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-white/10 font-medium text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <Icon className="size-4 shrink-0" />
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="rounded-pill bg-teal px-1.5 py-0.5 text-[10px] font-semibold text-white">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-white/10 p-3">
        <Link
          href="#"
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-white/60 transition-colors hover:bg-white/5 hover:text-white"
        >
          <Settings className="size-4" /> Settings
        </Link>
        <div className="mt-2 flex items-center gap-2 rounded-md bg-white/5 px-3 py-2">
          <div className="flex size-7 items-center justify-center rounded-full bg-teal text-xs font-semibold text-white">
            GC
          </div>
          <div className="min-w-0">
            <div className="truncate text-xs font-medium text-white">G. Cozzio</div>
            <div className="truncate text-[10px] text-white/50">Relationship Manager</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
