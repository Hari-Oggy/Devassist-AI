"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton, useUser } from "@clerk/nextjs";
import { 
  Search, 
  Layers, 
  LayoutDashboard, 
  Settings, 
  PieChart,
  ListTodo
} from "lucide-react";

const navigation = [
  { name: 'Overview', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Reviews', href: '/reviews', icon: ListTodo },
  { name: 'Repositories', href: '/repositories', icon: Layers },
  { name: 'Analytics', href: '/analytics', icon: PieChart },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, isLoaded } = useUser();

  return (
    <div className="flex h-full w-64 flex-col border-r border-zinc-800 bg-[#0d0d12]">
      <div className="flex h-16 items-center gap-2 px-6 border-b border-zinc-800/50">
        <div className="h-6 w-6 rounded-md bg-gradient-to-tr from-orange-600 to-amber-500 overflow-hidden flex items-center justify-center shadow-lg shadow-orange-900/20">
          <span className="font-bold text-[10px] text-white">DA</span>
        </div>
        <span className="font-bold text-sm tracking-tight text-zinc-100">DevAssist-AI</span>
      </div>
      
      <div className="px-4 pt-4 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search..."
            className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 py-2 pl-9 pr-3 text-sm text-zinc-300 placeholder:text-zinc-600 focus:border-zinc-700 focus:outline-none focus:ring-1 focus:ring-zinc-700 transition-all"
          />
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto scrollbar-hide">
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200 ${
                isActive 
                  ? "bg-zinc-800/80 text-white shadow-sm" 
                  : "text-zinc-400 hover:bg-zinc-800/40 hover:text-white"
              }`}
            >
              <item.icon className={`h-4 w-4 shrink-0 transition-colors ${isActive ? "text-orange-500" : "text-zinc-500 group-hover:text-zinc-300"}`} aria-hidden="true" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto p-4">
        <div className="rounded-xl border border-zinc-800/50 bg-gradient-to-b from-zinc-800/40 to-zinc-900/40 p-4 shadow-sm backdrop-blur-sm">
          <p className="text-xs font-semibold text-white">
            <span className="text-orange-500">DevAssist-AI</span> Pro
          </p>
          <p className="mt-1 text-[11px] text-zinc-400 leading-snug">
            You are using the ensemble review pipeline.
          </p>
        </div>
      </div>
      
      <div className="border-t border-zinc-800/80 p-4 bg-zinc-900/20">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0">
            <UserButton />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium text-zinc-200 truncate">
              {isLoaded && user ? user.fullName || user.username : "Loading..."}
            </span>
            <span className="text-[10px] text-zinc-500">Admin</span>
          </div>
        </div>
      </div>
    </div>
  );
}
