"use client";

import { useEffect } from "react";
import Link from "next/link";
import {
  Activity,
  FileCode2,
  ShieldAlert,
  Zap,
  ArrowRight,
  GitMerge,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Plus,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { useDashboardStore } from "@/lib/stores/dashboardStore";
import { MetricCard, PageHeader, GlassCard, LoadingSpinner, StatusBadge } from "@/components/ui/shared";

function formatTimeAgo(dateStr: string) {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    if (isNaN(diffMs) || diffMs < 0) return "Just now";
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return "Recently";
  }
}

const VULNERABILITY_COLORS = ["#f43f5e", "#f97316", "#eab308"];

export default function DashboardOverview() {
  const {
    statusData,
    analytics,
    reviews,
    trends,
    loadingAnalytics,
    loadingReviews,
    fetchStatus,
    fetchAnalytics,
    fetchReviews,
    fetchTrends,
  } = useDashboardStore();

  useEffect(() => {
    fetchStatus();
    fetchAnalytics();
    fetchReviews();
    fetchTrends();
  }, [fetchStatus, fetchAnalytics, fetchReviews, fetchTrends]);

  const successRate =
    analytics && analytics.reviews.total > 0
      ? Math.round((analytics.reviews.completed / analytics.reviews.total) * 100)
      : 100;

  // Build vulnerability donut data
  const vulnData = analytics
    ? [
        { name: "Critical", value: analytics.findings_by_severity.critical, color: "#f43f5e" },
        { name: "High", value: analytics.findings_by_severity.high, color: "#f97316" },
        { name: "Low", value: analytics.findings_by_severity.low + analytics.findings_by_severity.medium, color: "#eab308" },
      ].filter((d) => d.value > 0)
    : [];

  // Trend chart data (last 7 points)
  const trendSlice = trends.slice(-7).map((t) => ({
    date: t.date ? new Date(t.date).toLocaleDateString("en-US", { weekday: "short" }) : "",
    critical: t.critical,
    high: t.high,
    other: t.other,
  }));

  // Overall Code Health sparkline
  const healthData = trends.slice(-7).map((t, i) => ({
    index: i,
    value: Math.max(0, 100 - t.critical * 5 - t.high * 2),
  }));

  const codeHealthScore = analytics
    ? Math.max(
        0,
        100 -
          analytics.findings_by_severity.critical * 10 -
          analytics.findings_by_severity.high * 3
      )
    : null;

  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <PageHeader
        title="Dashboard"
        subtitle="Welcome back — here's what's happening across your code reviews."
        action={
          <Link href="/repositories">
            <button className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 px-5 py-2.5 text-[13px] font-bold text-white transition-all duration-200 shadow-lg shadow-violet-600/25">
              <Plus className="h-4 w-4" />
              Start New Review
            </button>
          </Link>
        }
      />

      {/* System Status Banner */}
      <GlassCard className="flex items-center justify-between overflow-hidden relative">
        <div className="absolute inset-0 bg-gradient-to-r from-violet-600/5 to-transparent pointer-events-none" />
        <div className="relative flex items-center gap-5">
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-2xl border ${
              statusData?.database
                ? "border-emerald-500/20 bg-emerald-500/10"
                : "border-amber-500/20 bg-amber-500/10"
            }`}
          >
            <Activity
              className={`h-6 w-6 ${statusData?.database ? "text-emerald-400" : "text-amber-400"}`}
            />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-[15px] font-bold text-white">System Status</h2>
              {statusData?.database && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
              )}
            </div>
            <p className={`text-[13px] font-medium ${statusData?.database ? "text-emerald-400" : "text-amber-400"}`}>
              {statusData ? "All systems operational" : "Checking connection..."}
            </p>
          </div>
        </div>
        <div className="relative hidden sm:flex flex-col items-end gap-1">
          <p className="text-[11px] text-white/40 font-medium uppercase tracking-wider">AI Model</p>
          <p className="text-[14px] font-bold text-white">
            {statusData?.llm_model || "—"}
          </p>
          <p className="text-[11px] text-violet-400 font-medium">
            {statusData?.llm_provider || ""}
          </p>
        </div>
      </GlassCard>

      {/* KPI Metrics Row */}
      <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Reviews"
          value={analytics ? analytics.reviews.total : "—"}
          icon={<GitMerge className="h-4 w-4" />}
          trend="All time reviews"
          accent="violet"
          isLoading={loadingAnalytics}
        />
        <MetricCard
          label="Active Repositories"
          value={analytics ? analytics.total_repositories : "—"}
          icon={<FileCode2 className="h-4 w-4" />}
          trend="Connected repos"
          accent="cyan"
          isLoading={loadingAnalytics}
        />
        <MetricCard
          label="Critical Findings"
          value={analytics ? (analytics.findings_by_severity.critical ?? 0) : "—"}
          icon={<ShieldAlert className="h-4 w-4" />}
          trend={(analytics?.findings_by_severity.critical ?? 0) > 0 ? "Needs attention" : "All clear"}
          trendUp={analytics ? (analytics.findings_by_severity.critical ?? 0) === 0 : undefined}
          accent="rose"
          isLoading={loadingAnalytics}
        />
        <MetricCard
          label="Success Rate"
          value={analytics ? `${successRate}%` : "—"}
          icon={<Zap className="h-4 w-4" />}
          trend="Completed vs total"
          trendUp={successRate >= 80}
          accent="emerald"
          isLoading={loadingAnalytics}
        />
      </div>

      {/* Charts Row */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Overall Code Health – Area Chart */}
        <GlassCard className="lg:col-span-2">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-[15px] font-bold text-white">Overall Code Health</h3>
              <p className="text-[12px] text-white/40 mt-0.5">Issues trend over time</p>
            </div>
            {codeHealthScore !== null && (
              <div className="text-right">
                <p className="text-[2rem] font-bold text-white leading-none">
                  {codeHealthScore}%
                </p>
                <p className="text-[11px] text-emerald-400 font-medium mt-0.5">
                  {codeHealthScore >= 80 ? "Healthy" : "Needs Attention"}
                </p>
              </div>
            )}
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendSlice.length > 0 ? trendSlice : healthData.map((d) => ({ date: String(d.index), critical: 0, high: 0, other: d.value }))}>
                <defs>
                  <linearGradient id="gradCritical" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#a855f7" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#a855f7" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradHigh" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} width={30} />
                <Tooltip
                  contentStyle={{
                    background: "#1a1a2e",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "12px",
                    padding: "10px 14px",
                    color: "#fff",
                    fontSize: "12px",
                  }}
                  itemStyle={{ color: "rgba(255,255,255,0.7)" }}
                  cursor={{ stroke: "rgba(255,255,255,0.1)", strokeWidth: 1 }}
                />
                <Area type="monotone" dataKey="critical" stroke="#a855f7" strokeWidth={2.5} fill="url(#gradCritical)" name="Critical" />
                <Area type="monotone" dataKey="high" stroke="#06b6d4" strokeWidth={2} fill="url(#gradHigh)" name="High" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex items-center gap-4 mt-4">
            <div className="flex items-center gap-1.5 text-[11px] text-white/50 font-medium">
              <span className="h-2 w-2 rounded-full bg-violet-500" />
              Critical
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-white/50 font-medium">
              <span className="h-2 w-2 rounded-full bg-cyan-500" />
              High
            </div>
          </div>
        </GlassCard>

        {/* Vulnerability Breakdown – Donut */}
        <GlassCard>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[15px] font-bold text-white">Vulnerability Breakdown</h3>
          </div>
          {vulnData.length > 0 ? (
            <>
              <div className="relative h-44 flex items-center justify-center">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={vulnData}
                      cx="50%"
                      cy="50%"
                      innerRadius={52}
                      outerRadius={72}
                      paddingAngle={3}
                      dataKey="value"
                      strokeWidth={0}
                    >
                      {vulnData.map((entry, index) => (
                        <Cell key={index} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#1a1a2e",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: "10px",
                        fontSize: "12px",
                        color: "#fff",
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <p className="text-[22px] font-bold text-white">
                    {analytics?.total_findings ?? 0}
                  </p>
                  <p className="text-[10px] text-white/40 font-medium uppercase tracking-wider">Total</p>
                </div>
              </div>
              <div className="space-y-2 mt-3">
                {vulnData.map((d) => (
                  <div key={d.name} className="flex items-center justify-between text-[12px]">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                      <span className="text-white/60 font-medium">{d.name}</span>
                    </div>
                    <span className="font-bold text-white">{d.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="h-44 flex flex-col items-center justify-center gap-3">
              <CheckCircle2 className="h-10 w-10 text-emerald-500/60" />
              <p className="text-[13px] text-white/40 text-center">No vulnerabilities found</p>
            </div>
          )}
        </GlassCard>
      </div>

      {/* Recent Activity */}
      <GlassCard noPad>
        <div className="p-6 flex items-center justify-between border-b border-white/[0.06]">
          <div>
            <h3 className="text-[15px] font-bold text-white">Recent Activity</h3>
            <p className="text-[12px] text-white/40 mt-0.5">Latest automated PR reviews</p>
          </div>
          <Link
            href="/reviews"
            className="flex items-center gap-1.5 text-[12px] font-bold text-violet-400 hover:text-violet-300 transition-colors"
          >
            View all <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="divide-y divide-white/[0.05]">
          {loadingReviews ? (
            <div className="p-8 flex items-center justify-center">
              <LoadingSpinner />
            </div>
          ) : reviews.length === 0 ? (
            <div className="p-10 text-center">
              <FileCode2 className="h-10 w-10 text-white/15 mx-auto mb-3" />
              <p className="text-[14px] text-white/30 font-medium">No recent activity found.</p>
              <p className="text-[12px] text-white/20 mt-1">Connect a repository to get started.</p>
            </div>
          ) : (
            reviews.slice(0, 5).map((r) => {
              const statusIcon = (() => {
                switch (r.status?.toLowerCase()) {
                  case "completed": return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
                  case "running": return <Loader2 className="h-4 w-4 text-violet-400 animate-spin" />;
                  case "failed": return <XCircle className="h-4 w-4 text-rose-400" />;
                  default: return <Clock className="h-4 w-4 text-white/30" />;
                }
              })();

              return (
                <div
                  key={r.id}
                  className="flex items-center justify-between px-6 py-4 hover:bg-white/[0.02] transition-colors group"
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="h-10 w-10 rounded-xl bg-white/[0.04] border border-white/[0.07] flex items-center justify-center shrink-0">
                      {statusIcon}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[14px] font-semibold text-white truncate group-hover:text-violet-300 transition-colors">
                        {r.pr_title || `Review #${r.id}`}
                      </p>
                      <p className="text-[12px] text-white/40 font-mono mt-0.5 truncate">
                        {r.repo_name || "Unknown Repo"} · {formatTimeAgo(r.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {r.total_findings > 0 ? (
                      <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-500/10 border border-rose-500/20 text-[11px] font-bold text-rose-400">
                        <ShieldAlert className="h-3 w-3" />
                        {r.total_findings} issue{r.total_findings !== 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[11px] font-bold text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" />
                        Clean
                      </span>
                    )}
                    <StatusBadge status={r.status} />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </GlassCard>

      {/* Codebase Metrics Bottom Row */}
      {analytics && (
        <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
          <GlassCard className="col-span-2 lg:col-span-2 flex items-center gap-6">
            <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center shrink-0">
              <ShieldAlert className="h-6 w-6 text-violet-400" />
            </div>
            <div>
              <p className="text-[12px] text-white/40 font-medium uppercase tracking-wider mb-1">Total AI Findings</p>
              <p className="text-[2rem] font-bold text-white leading-none">
                {analytics.total_findings}
              </p>
              <p className="text-[12px] text-white/40 mt-1">
                ~{analytics.avg_findings_per_review.toFixed(1)} per review
              </p>
            </div>
          </GlassCard>

          <GlassCard className="flex items-center gap-5">
            <div>
              <p className="text-[12px] text-white/40 uppercase tracking-wider font-medium mb-1">Avg Resolution</p>
              <p className="text-[1.6rem] font-bold text-white leading-none">
                {analytics.avg_resolution_time ? `${analytics.avg_resolution_time}s` : "—"}
              </p>
              <p className="text-[11px] text-emerald-400 font-medium mt-1">Processing time</p>
            </div>
          </GlassCard>

          <GlassCard className="flex items-center gap-5">
            <div>
              <p className="text-[12px] text-white/40 uppercase tracking-wider font-medium mb-1">Failed Reviews</p>
              <p className={`text-[1.6rem] font-bold leading-none ${analytics.reviews.failed > 0 ? "text-rose-400" : "text-white"}`}>
                {analytics.reviews.failed}
              </p>
              <p className="text-[11px] text-white/30 font-medium mt-1">of {analytics.reviews.total} total</p>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
