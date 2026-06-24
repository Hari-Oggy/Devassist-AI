"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Activity, GitMerge, FileCode2, Zap, ArrowRight, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { readJson } from "@/lib/api";

interface StatusData {
  status: string;
  database: boolean;
  llm_provider: string;
  llm_model: string;
  version: string;
}

export default function DashboardOverview() {
  const [statusData, setStatusData] = useState<StatusData | null>(null);

  useEffect(() => {
    fetch("/api/v3/status")
      .then(res => readJson<StatusData>(res))
      .then(data => setStatusData(data))
      .catch(console.error);
  }, []);

  return (
    <div className="mx-auto max-w-5xl p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-6">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Overview</h1>
          <p className="text-zinc-400 mt-1">Welcome to the DevAssist-AI command center.</p>
        </div>
        <Link href="/repositories">
          <Button className="bg-orange-600 hover:bg-orange-700 text-white shadow-lg shadow-orange-900/20">
            <GitMerge className="mr-2 h-4 w-4" />
            Connect Repository
          </Button>
        </Link>
      </div>

      {/* System Status Banner */}
      <Card className="bg-gradient-to-r from-zinc-900/80 to-zinc-900/40 border-zinc-800/80 p-6 overflow-hidden relative">
        <div className="absolute right-0 top-0 w-64 h-64 bg-orange-500/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
        
        <div className="flex items-center justify-between relative z-10">
          <div className="flex items-center gap-4">
            <div className={`flex h-12 w-12 items-center justify-center rounded-full border-2 ${statusData?.database ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-amber-500/30 bg-amber-500/10'}`}>
              <Activity className={`h-6 w-6 ${statusData?.database ? 'text-emerald-500' : 'text-amber-500'}`} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                System Status
                {statusData?.database && (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                )}
              </h2>
              <p className="text-sm text-zinc-400 mt-0.5">
                {statusData 
                  ? `Connected to PostgreSQL. Running v${statusData.version} with ${statusData.llm_provider}`
                  : "Checking connection..."}
              </p>
            </div>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-1">Active Model</p>
            <p className="text-sm font-medium text-zinc-300 bg-zinc-800/50 px-3 py-1 rounded-full border border-zinc-700/50">
              {statusData?.llm_model || "Loading..."}
            </p>
          </div>
        </div>
      </Card>

      {/* Quick Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="bg-zinc-900/50 border-zinc-800 p-6 hover:bg-zinc-900/80 transition-colors">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-500/10 rounded-xl text-blue-500">
              <GitMerge className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-400">Total Reviews</p>
              <h3 className="text-2xl font-bold text-white mt-1">--</h3>
            </div>
          </div>
        </Card>
        
        <Card className="bg-zinc-900/50 border-zinc-800 p-6 hover:bg-zinc-900/80 transition-colors">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-purple-500/10 rounded-xl text-purple-500">
              <FileCode2 className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-400">Active Repositories</p>
              <h3 className="text-2xl font-bold text-white mt-1">--</h3>
            </div>
          </div>
        </Card>

        <Card className="bg-zinc-900/50 border-zinc-800 p-6 hover:bg-zinc-900/80 transition-colors">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-red-500/10 rounded-xl text-red-500">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-400">Critical Findings</p>
              <h3 className="text-2xl font-bold text-white mt-1">--</h3>
            </div>
          </div>
        </Card>
      </div>

      {/* Recent Activity */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-zinc-200">Recent Activity</h3>
          <Link href="/reviews">
            <Button variant="ghost" className="text-sm text-orange-500 hover:text-orange-400 hover:bg-orange-500/10">
              View all <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          </Link>
        </div>
        <Card className="bg-zinc-900/30 border-zinc-800/60 p-8 flex flex-col items-center justify-center text-center">
          <div className="h-12 w-12 rounded-full bg-zinc-800/50 flex items-center justify-center mb-4">
            <Zap className="h-6 w-6 text-zinc-500" />
          </div>
          <h4 className="text-zinc-300 font-medium mb-1">No recent reviews</h4>
          <p className="text-sm text-zinc-500 max-w-sm">
            Once you connect a repository and open a pull request, your review history will appear here.
          </p>
        </Card>
      </div>
    </div>
  );
}
