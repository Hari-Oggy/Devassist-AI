"use client";

import { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  trend?: string;
  trendUp?: boolean;
  accent?: "violet" | "cyan" | "emerald" | "rose" | "amber";
  isLoading?: boolean;
}

const accentMap = {
  violet: {
    bg: "bg-violet-500/10",
    border: "border-violet-500/20",
    icon: "text-violet-400",
    glow: "group-hover:shadow-[0_8px_30px_-8px_rgba(139,92,246,0.25)]",
    dot: "bg-violet-500",
  },
  cyan: {
    bg: "bg-cyan-500/10",
    border: "border-cyan-500/20",
    icon: "text-cyan-400",
    glow: "group-hover:shadow-[0_8px_30px_-8px_rgba(6,182,212,0.25)]",
    dot: "bg-cyan-500",
  },
  emerald: {
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
    icon: "text-emerald-400",
    glow: "group-hover:shadow-[0_8px_30px_-8px_rgba(16,185,129,0.25)]",
    dot: "bg-emerald-500",
  },
  rose: {
    bg: "bg-rose-500/10",
    border: "border-rose-500/20",
    icon: "text-rose-400",
    glow: "group-hover:shadow-[0_8px_30px_-8px_rgba(244,63,94,0.25)]",
    dot: "bg-rose-500",
  },
  amber: {
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
    icon: "text-amber-400",
    glow: "group-hover:shadow-[0_8px_30px_-8px_rgba(245,158,11,0.25)]",
    dot: "bg-amber-500",
  },
};

export function MetricCard({
  label,
  value,
  icon,
  trend,
  trendUp,
  accent = "violet",
  isLoading = false,
}: MetricCardProps) {
  const colors = accentMap[accent];

  return (
    <div
      className={`group relative rounded-2xl border bg-white/[0.03] border-white/[0.07] p-5 overflow-hidden metric-card transition-shadow duration-300 ${colors.glow}`}
    >
      {/* Gradient orb */}
      <div
        className={`absolute -top-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-20 ${colors.dot}`}
      />

      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <p className="text-[13px] font-medium text-white/50">{label}</p>
          <div
            className={`p-2 rounded-xl border ${colors.bg} ${colors.border} ${colors.icon}`}
          >
            {icon}
          </div>
        </div>

        {isLoading ? (
          <div className="h-9 w-20 bg-white/[0.06] rounded-lg animate-pulse" />
        ) : (
          <p className="text-[2rem] font-bold text-white tracking-tight leading-none">
            {value}
          </p>
        )}

        {trend && !isLoading && (
          <p
            className={`text-[12px] font-medium mt-2 flex items-center gap-1 ${
              trendUp === undefined
                ? "text-white/40"
                : trendUp
                ? "text-emerald-400"
                : "text-rose-400"
            }`}
          >
            {trendUp !== undefined && (
              <span className="text-[10px]">{trendUp ? "↑" : "↓"}</span>
            )}
            {trend}
          </p>
        )}
      </div>
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between pb-2">
      <div>
        <h1 className="text-[1.75rem] font-bold text-white tracking-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="text-white/40 mt-1.5 text-[14px] font-medium">
            {subtitle}
          </p>
        )}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  noPad?: boolean;
}

export function GlassCard({ children, className = "", noPad = false }: GlassCardProps) {
  return (
    <div
      className={`rounded-2xl border border-white/[0.07] bg-white/[0.03] ${
        noPad ? "" : "p-6"
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizeMap = { sm: "h-5 w-5", md: "h-8 w-8", lg: "h-12 w-12" };
  return (
    <div
      className={`animate-spin rounded-full border-2 border-white/10 border-t-violet-500 ${sizeMap[size]}`}
    />
  );
}

export function StatusBadge({ status }: { status: string }) {
  const s = status?.toLowerCase();
  const map: Record<string, string> = {
    completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    running: "bg-violet-500/10 text-violet-400 border-violet-500/20",
    failed: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    active: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    pending: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-bold uppercase tracking-wider ${
        map[s] || "bg-white/5 text-white/50 border-white/10"
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}
