"use client";

import { useEffect } from "react";
import {
  TrendingUp,
  ShieldAlert,
  CheckCircle2,
  GitMerge,
  Clock,
  BarChart3,
  AlertTriangle,
  Activity,
  Calendar,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { useDashboardStore } from "@/lib/stores/dashboardStore";
import {
  MetricCard,
  PageHeader,
  GlassCard,
  LoadingSpinner,
} from "@/components/ui/shared";
import { Button } from "@/components/ui/button";

function formatDateShort(dateStr?: string) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return dateStr;
  }
}

const TOOLTIP_STYLE = {
  background: "#13131f",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: "12px",
  padding: "10px 14px",
  color: "#fff",
  fontSize: "12px",
  boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
};

const ITEM_STYLE = { color: "rgba(255,255,255,0.65)" };

export default function AnalyticsPage() {
  const {
    analytics,
    trends,
    loadingAnalytics,
    loadingTrends,
    fetchAnalytics,
    fetchTrends,
  } = useDashboardStore();

  useEffect(() => {
    fetchAnalytics();
    fetchTrends();
  }, [fetchAnalytics, fetchTrends]);

  const loading = loadingAnalytics;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[60vh]">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const data = analytics ?? {
    reviews: { total: 0, completed: 0, failed: 0, running: 0 },
    findings_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
    findings_by_category: [],
    total_findings: 0,
    total_repositories: 0,
    avg_findings_per_review: 0,
    avg_resolution_time: 0,
  };

  const totalFindings = data.total_findings;
  const sev = data.findings_by_severity;
  const rev = data.reviews;
  const successRate = rev.total > 0 ? Math.round((rev.completed / rev.total) * 100) : 0;

  // Chart datasets
  const trendChartData = trends.map((t) => ({
    date: formatDateShort(t.date),
    critical: t.critical,
    high: t.high,
    other: t.other,
  }));

  const severityBarData = [
    { name: "Critical", value: sev.critical, fill: "#f43f5e" },
    { name: "High", value: sev.high, fill: "#f97316" },
    { name: "Medium", value: sev.medium, fill: "#eab308" },
    { name: "Low", value: sev.low, fill: "#6366f1" },
  ];

  const pipelineData = [
    { name: "Completed", value: rev.completed, fill: "#10b981" },
    { name: "Running", value: rev.running, fill: "#a855f7" },
    { name: "Failed", value: rev.failed, fill: "#f43f5e" },
  ];

  const categoryData = data.findings_by_category.slice(0, 8).map((c) => ({
    name: c.name.length > 14 ? c.name.slice(0, 14) + "…" : c.name,
    value: c.count,
    fill: "#6366f1",
  }));

  // Radial health metrics
  const radialData = [
    { name: "Success Rate", value: successRate, fill: "#10b981" },
    {
      name: "Code Coverage",
      value: totalFindings > 0 ? Math.max(0, 100 - (sev.critical * 5)) : 95,
      fill: "#a855f7",
    },
    {
      name: "Security",
      value: totalFindings > 0 ? Math.max(0, 100 - sev.critical * 10 - sev.high * 3) : 100,
      fill: "#06b6d4",
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <PageHeader
        title="Analytics Overview"
        subtitle="Deep insights into your code review performance and findings."
        action={
          <Button
            variant="outline"
            className="bg-white/[0.03] hover:bg-white/[0.06] text-white/70 border-white/10 shadow-sm h-10 px-4 rounded-xl text-[13px] font-medium gap-2"
          >
            <Calendar className="h-4 w-4 text-white/40" />
            Past 30 Days
          </Button>
        }
      />

      {/* KPI Grid */}
      <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total PRs Reviewed"
          value={rev.total}
          icon={<GitMerge className="h-4 w-4" />}
          trend={`+${rev.completed} completed`}
          trendUp
          accent="violet"
        />
        <MetricCard
          label="AI Findings"
          value={totalFindings}
          icon={<ShieldAlert className="h-4 w-4" />}
          trend="Issues identified"
          trendUp={totalFindings === 0}
          accent="rose"
        />
        <MetricCard
          label="Avg. Resolution"
          value={data.avg_resolution_time ? `${data.avg_resolution_time}s` : "—"}
          icon={<Clock className="h-4 w-4" />}
          trend="Processing time"
          accent="cyan"
        />
        <MetricCard
          label="Review Success Rate"
          value={`${successRate}%`}
          icon={<CheckCircle2 className="h-4 w-4" />}
          trend="Completed vs total"
          trendUp={successRate >= 70}
          accent="emerald"
        />
      </div>

      {/* Main Trend Chart */}
      <GlassCard>
        <div className="flex items-center justify-between mb-8">
          <div>
            <h3 className="text-[16px] font-bold text-white">Code Quality Over Time</h3>
            <p className="text-[12px] text-white/40 mt-1">Daily trend of code review findings by severity</p>
          </div>
          <div className="flex items-center gap-5 text-[12px] font-medium">
            <span className="flex items-center gap-2 text-violet-400">
              <span className="h-2.5 w-2.5 rounded-full bg-violet-500" />
              Critical
            </span>
            <span className="flex items-center gap-2 text-orange-400">
              <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
              High
            </span>
            <span className="flex items-center gap-2 text-white/40">
              <span className="h-2.5 w-2.5 rounded-full bg-white/30" />
              Other
            </span>
          </div>
        </div>

        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trendChartData}>
              <defs>
                <linearGradient id="gcritical" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a855f7" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#a855f7" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="ghigh" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f97316" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gother" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#94a3b8" stopOpacity={0.1} />
                  <stop offset="100%" stopColor="#94a3b8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={28}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={ITEM_STYLE} cursor={{ stroke: "rgba(255,255,255,0.08)", strokeWidth: 1 }} />
              <Area type="monotone" dataKey="critical" stroke="#a855f7" strokeWidth={2.5} fill="url(#gcritical)" name="Critical" dot={{ fill: "#a855f7", strokeWidth: 0, r: 3 }} activeDot={{ r: 5, fill: "#a855f7" }} />
              <Area type="monotone" dataKey="high" stroke="#f97316" strokeWidth={2} fill="url(#ghigh)" name="High" strokeDasharray="5 4" dot={false} />
              <Area type="monotone" dataKey="other" stroke="#94a3b8" strokeWidth={1.5} fill="url(#gother)" name="Other" dot={false} opacity={0.7} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      {/* Middle Row: Severity Bars + Category Bars */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Severity Breakdown – Horizontal Bar */}
        <GlassCard>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20">
              <ShieldAlert className="h-4 w-4 text-rose-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white">By Severity</h3>
              <p className="text-[11px] text-white/40">Total: {totalFindings} findings</p>
            </div>
          </div>
          <div className="space-y-5">
            {[
              { label: "Critical", count: sev.critical, color: "#f43f5e", bg: "bg-rose-500/10 border-rose-500/20 text-rose-400" },
              { label: "High", count: sev.high, color: "#f97316", bg: "bg-orange-500/10 border-orange-500/20 text-orange-400" },
              { label: "Medium", count: sev.medium, color: "#eab308", bg: "bg-amber-500/10 border-amber-500/20 text-amber-400" },
              { label: "Low", count: sev.low, color: "#6366f1", bg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-400" },
            ].map((item) => {
              const pct = totalFindings > 0 ? Math.round((item.count / totalFindings) * 100) : 0;
              return (
                <div key={item.label} className="space-y-2">
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="font-semibold text-white/70">{item.label}</span>
                    <span className="font-bold text-white">{item.count} <span className="text-white/30 font-medium">({pct}%)</span></span>
                  </div>
                  <div className="h-2 rounded-full bg-white/[0.05] overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${pct}%`, background: item.color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>

        {/* Top Issue Types – Bar chart */}
        <GlassCard>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-violet-500/10 border border-violet-500/20">
              <BarChart3 className="h-4 w-4 text-violet-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white">Top Issue Types</h3>
              <p className="text-[11px] text-white/40">By category</p>
            </div>
          </div>
          {categoryData.length > 0 ? (
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis dataKey="name" type="category" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} axisLine={false} tickLine={false} width={90} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={ITEM_STYLE} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                  <Bar dataKey="value" radius={[0, 6, 6, 0]} name="Count">
                    {categoryData.map((entry, index) => (
                      <Cell key={index} fill={`hsl(${265 + index * 20}, 70%, 65%)`} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-52 flex flex-col items-center justify-center gap-3">
              <BarChart3 className="h-10 w-10 text-white/15" />
              <p className="text-[13px] text-white/30">No category data available</p>
            </div>
          )}
        </GlassCard>
      </div>

      {/* Bottom Row: Pipeline Status + Radial Health */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Pipeline Status Bar */}
        <GlassCard className="lg:col-span-2">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20">
              <Activity className="h-4 w-4 text-cyan-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white">Review Trends</h3>
              <p className="text-[11px] text-white/40">Pipeline health over time</p>
            </div>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trendChartData.length > 0 ? trendChartData : [{ date: "Now", critical: sev.critical, high: sev.high, other: sev.low + sev.medium }]}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={ITEM_STYLE} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                <Bar dataKey="critical" fill="#a855f7" radius={[4, 4, 0, 0]} name="Critical" />
                <Bar dataKey="high" fill="#06b6d4" radius={[4, 4, 0, 0]} name="High" />
                <Bar dataKey="other" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Other" opacity={0.5} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-4 mt-4">
            {pipelineData.map((p) => (
              <div key={p.name} className="flex items-center gap-1.5 text-[11px] text-white/50 font-medium">
                <span className="h-2 w-2 rounded-full" style={{ background: p.fill }} />
                {p.name}: <span className="text-white font-bold ml-0.5">{p.value}</span>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Radial Health Metrics */}
        <GlassCard>
          <h3 className="text-[15px] font-bold text-white mb-6">Health Metrics</h3>
          <div className="h-44 relative">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="30%"
                outerRadius="100%"
                data={radialData}
                startAngle={180}
                endAngle={0}
              >
                <RadialBar dataKey="value" cornerRadius={6} background={{ fill: "rgba(255,255,255,0.04)" }} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(value) => [`${value != null ? Math.round(Number(value)) : 0}%`, ""]}
                />
              </RadialBarChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-3 mt-2">
            {radialData.map((d) => (
              <div key={d.name} className="flex items-center justify-between text-[12px]">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: d.fill }} />
                  <span className="text-white/50">{d.name}</span>
                </div>
                <span className="font-bold text-white">{d.value}%</span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Summary Stats Grid */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: "Success Rate",
            value: `${successRate}%`,
            color: "text-emerald-400",
            bg: "bg-emerald-500/10",
            border: "border-emerald-500/20",
            icon: <CheckCircle2 className="h-5 w-5 text-emerald-400" />,
          },
          {
            label: "Avg Findings",
            value: data.avg_findings_per_review.toFixed(1),
            color: "text-amber-400",
            bg: "bg-amber-500/10",
            border: "border-amber-500/20",
            icon: <TrendingUp className="h-5 w-5 text-amber-400" />,
          },
          {
            label: "Critical Issues",
            value: sev.critical,
            color: "text-rose-400",
            bg: "bg-rose-500/10",
            border: "border-rose-500/20",
            icon: <AlertTriangle className="h-5 w-5 text-rose-400" />,
          },
          {
            label: "Active Repos",
            value: data.total_repositories,
            color: "text-violet-400",
            bg: "bg-violet-500/10",
            border: "border-violet-500/20",
            icon: <GitMerge className="h-5 w-5 text-violet-400" />,
          },
        ].map((item) => (
          <div
            key={item.label}
            className={`rounded-2xl border ${item.bg} ${item.border} p-5 flex flex-col items-center justify-center text-center gap-3`}
          >
            {item.icon}
            <span className={`text-[2rem] font-bold leading-none ${item.color}`}>{item.value}</span>
            <span className="text-[11px] font-medium text-white/40 uppercase tracking-wider">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
