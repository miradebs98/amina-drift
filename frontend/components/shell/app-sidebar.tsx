"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Users, Bell, ScrollText, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { AminaLogo } from "./amina-logo";

const NAV = [
  { label: "Client Portfolio", href: "/dashboard", icon: Users },
  { label: "Alerts", href: "/alerts", icon: Bell },
  { label: "Audit log", href: "/audit", icon: ScrollText },
];

const STORAGE_KEY = "amina-sidebar-collapsed";

export function AppSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  // persist collapse state across navigations
  useEffect(() => {
    setCollapsed(localStorage.getItem(STORAGE_KEY) === "1");
  }, []);
  function toggle() {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <aside
      className={`sticky top-0 hidden h-screen shrink-0 flex-col border-r border-brand-deep/40 bg-brand text-white transition-[width] duration-200 md:flex ${
        collapsed ? "w-[64px]" : "w-[220px]"
      }`}
    >
      {/* brand + collapse toggle */}
      <div className={`flex items-center pt-5 ${collapsed ? "flex-col gap-3 px-2" : "justify-between px-5"}`}>
        {!collapsed && (
          <Link href="/dashboard" className="block">
            <AminaLogo className="h-6 w-auto text-white" />
          </Link>
        )}
        <button
          onClick={toggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex size-8 items-center justify-center rounded-md text-white/60 transition-colors hover:bg-white/10 hover:text-white"
        >
          {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
        </button>
      </div>
      {!collapsed && (
        <div className="px-5 pb-3 pt-1 text-[10px] uppercase tracking-[0.18em] text-teal-bright">Drift Intelligence</div>
      )}

      <nav className={`flex-1 space-y-0.5 py-3 ${collapsed ? "px-2" : "px-3"}`}>
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`flex items-center gap-3 rounded-md py-2 text-sm transition-colors ${
                collapsed ? "justify-center px-0" : "px-3"
              } ${active ? "bg-white/10 font-medium text-white" : "text-white/60 hover:bg-white/5 hover:text-white"}`}
            >
              <Icon className="size-4 shrink-0" />
              {!collapsed && <span className="flex-1">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* user */}
      <div className={`border-t border-white/10 p-3 ${collapsed ? "flex justify-center" : ""}`}>
        <div className={`flex items-center gap-2 rounded-md bg-white/5 ${collapsed ? "p-1.5" : "px-3 py-2"}`}>
          <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-teal text-xs font-semibold text-white">
            GC
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate text-xs font-medium text-white">G. Cozzio</div>
              <div className="truncate text-[10px] text-white/50">Relationship Manager</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
