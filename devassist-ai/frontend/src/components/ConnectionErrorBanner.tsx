"use client";

import { useEffect } from "react";
import { useDashboardStore } from "@/lib/stores/dashboardStore";
import { AlertTriangle, X, RefreshCw } from "lucide-react";

export function ConnectionErrorBanner() {
  const { connectionError, clearConnectionError, fetchStatus } = useDashboardStore();

  if (!connectionError) return null;

  return (
    <div className="mx-6 mt-4 flex items-center gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/[0.06] px-5 py-3.5 backdrop-blur-sm">
      <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-bold text-amber-400">Backend connection error</p>
        <p className="text-[12px] text-amber-400/60 font-medium mt-0.5 truncate">
          {connectionError}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={fetchStatus}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[12px] font-bold text-amber-400 hover:bg-amber-500/20 transition-all"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </button>
        <button
          onClick={clearConnectionError}
          className="p-2 rounded-xl text-amber-400/50 hover:text-amber-400 hover:bg-amber-500/10 transition-all"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
