"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield } from "lucide-react";
import {
  Search,
  LayoutDashboard,
  Settings,
  BarChart3,
  ListTodo,
  GitBranch,
  HelpCircle,
  Zap,
  ChevronRight,
} from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Reviews", href: "/reviews", icon: ListTodo },
  { name: "Repositories", href: "/repositories", icon: GitBranch },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Settings", href: "/settings", icon: Settings },
];

const bottomNav = [
  { name: "Help & Docs", href: "#", icon: HelpCircle },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-[220px] shrink-0 flex-col bg-[#0d0d14] border-r border-white/[0.06]">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-5 border-b border-white/[0.06]">
        <div className="relative h-8 w-8 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-600/30">
          <Zap className="h-4 w-4 text-white" />
          <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-violet-400/20 to-transparent" />
        </div>
        <div>
          <span className="font-bold text-[14px] tracking-tight text-white leading-none block">
            DevAssist
          </span>
          <span className="text-[10px] font-medium text-violet-400 tracking-widest uppercase leading-none">
            AI
          </span>
        </div>
      </div>

      {/* Search */}
      <div className="px-4 pt-5 pb-2">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30 group-focus-within:text-violet-400 transition-colors duration-200" />
          <input
            type="text"
            placeholder="Search..."
            className="w-full rounded-lg border border-white/[0.07] bg-white/[0.04] py-2 pl-8 pr-3 text-[13px] text-white/80 placeholder:text-white/25 focus:border-violet-500/40 focus:outline-none focus:ring-1 focus:ring-violet-500/30 transition-all duration-200"
          />
        </div>
      </div>

      {/* Nav label */}
      <div className="px-5 pt-4 pb-1">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-white/25">
          Navigation
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 px-3 py-2 overflow-y-auto">
        {navigation.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all duration-200 ${
                isActive
                  ? "bg-violet-600/15 text-white sidebar-active"
                  : "text-white/50 hover:bg-white/[0.04] hover:text-white/80"
              }`}
            >
              <item.icon
                className={`h-4 w-4 shrink-0 transition-colors duration-200 ${
                  isActive
                    ? "text-violet-400"
                    : "text-white/35 group-hover:text-white/60"
                }`}
                aria-hidden="true"
              />
              <span className="flex-1">{item.name}</span>
              {isActive && (
                <ChevronRight className="h-3.5 w-3.5 text-violet-400/60 shrink-0" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Bottom nav */}
      <div className="px-3 pb-2 space-y-0.5">
        {bottomNav.map((item) => (
          <Link
            key={item.name}
            href={item.href}
            className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium text-white/35 hover:bg-white/[0.04] hover:text-white/70 transition-all duration-200"
          >
            <item.icon className="h-4 w-4 shrink-0 text-white/25 group-hover:text-white/50 transition-colors" />
            {item.name}
          </Link>
        ))}
      </div>

      {/* Upgrade card */}
      <div className="p-3">
        <div className="relative rounded-2xl overflow-hidden p-[1px] bg-gradient-to-br from-violet-600/50 via-indigo-600/30 to-cyan-600/20">
          <div className="absolute inset-0 bg-gradient-to-br from-violet-600/10 to-indigo-900/30" />
          <div className="relative rounded-2xl bg-[#0d0d14]/80 backdrop-blur-xl p-4 flex flex-col gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-violet-600/20 border border-violet-500/20 flex items-center justify-center">
              <Zap className="h-4 w-4 text-violet-400" />
            </div>
            <div>
              <p className="text-[13px] font-bold text-white">Upgrade to Pro</p>
              <p className="mt-0.5 text-[11px] text-white/40 leading-relaxed">
                Unlock advanced insights & priority support.
              </p>
            </div>
            <button className="w-full rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 px-3 py-2 text-[11px] font-bold text-white transition-all duration-200 shadow-lg shadow-violet-600/20">
              Upgrade Now →
            </button>
          </div>
        </div>
      </div>

      {/* User profile — no-auth local admin */}
      <div className="border-t border-white/[0.06] p-4 bg-white/[0.01]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex-shrink-0 relative">
              <div className="h-8 w-8 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
                <Shield className="h-4 w-4 text-violet-400" />
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-[#0d0d14]" />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-[13px] font-semibold text-white truncate">
                Local Admin
              </span>
              <span className="text-[10px] font-medium text-violet-400/70 uppercase tracking-wider">
                Self-hosted
              </span>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
