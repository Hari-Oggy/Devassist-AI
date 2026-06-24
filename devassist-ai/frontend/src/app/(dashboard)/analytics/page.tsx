"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  TrendingUp,
  ShieldAlert,
  CheckCircle2,
  GitMerge,
  FileCode2,
  Clock,
  BarChart3,
  AlertTriangle,
  Bug,
  Zap,
  Lock,
} from "lucide-react";
import { readJson } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReviewStats {
  total: number;
  completed: number;
  failed: number;
  running: number;
}

interface FindingSeverity {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

interface FindingCategory {
  name: string;
  count: number;
}

interface AnalyticsData {
  reviews: ReviewStats;
  findings_by_severity: FindingSeverity;
  findings_by_category: FindingCategory[];
  total_findings: number;
  total_repositories: number;
  avg_findings_per_review: number;
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  subtext,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color: string;
  subtext?: string;
}) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800 p-6 hover:bg-zinc-900/80 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-400">{label}</p>
          <h3 className="text-3xl font-bold text-white mt-2">{value}</h3>
          {subtext && <p className="text-xs text-zinc-500 mt-1">{subtext}</p>}
        </div>
        <div className={`p-3 rounded-xl ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </Card>
  );
}

function SeverityBar({
  label,
  count,
  total,
  color,
  icon: Icon,
}: {
  label: string;
  count: number;
  total: number;
  color: string;
  icon: React.ElementType;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-4">
      <div className={`p-2 rounded-lg ${color} shrink-0`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between mb-1.5">
          <span className="text-sm font-medium text-zinc-300">{label}</span>
          <span className="text-sm font-mono text-zinc-400">
            {count} <span className="text-zinc-600">({pct}%)</span>
          </span>
        </div>
        <Progress value={pct} className="h-1.5 bg-zinc-800" />
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v3/analytics")
      .then((res) => readJson<AnalyticsData>(res))
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => {
        // Fall back to empty/demo state
        setData({
          reviews: { total: 0, completed: 0, failed: 0, running: 0 },
          findings_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
          findings_by_category: [],
          total_findings: 0,
          total_repositories: 0,
          avg_findings_per_review: 0,
        });
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500" />
      </div>
    );
  }

  const totalFindings = data!.total_findings;
  const sev = data!.findings_by_severity;
  const rev = data!.reviews;
  const successRate =
    rev.total > 0 ? Math.round((rev.completed / rev.total) * 100) : 0;

  return (
    <div className="mx-auto max-w-5xl p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-6">
        <h1 className="text-3xl font-bold text-white tracking-tight">Analytics</h1>
        <p className="text-zinc-400 mt-1">
          Insights into your code review pipeline and findings.
        </p>
      </div>

      {/* KPI Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Reviews"
          value={rev.total}
          icon={GitMerge}
          color="bg-blue-500/10 text-blue-400"
          subtext={`${successRate}% success rate`}
        />
        <StatCard
          label="Total Findings"
          value={totalFindings}
          icon={ShieldAlert}
          color="bg-red-500/10 text-red-400"
          subtext={`Avg ${data!.avg_findings_per_review.toFixed(1)} per review`}
        />
        <StatCard
          label="Repositories"
          value={data!.total_repositories}
          icon={FileCode2}
          color="bg-purple-500/10 text-purple-400"
        />
        <StatCard
          label="Completed"
          value={rev.completed}
          icon={CheckCircle2}
          color="bg-emerald-500/10 text-emerald-400"
          subtext={`${rev.failed} failed · ${rev.running} running`}
        />
      </div>

      <Tabs defaultValue="findings" className="space-y-6">
        <TabsList className="bg-zinc-900/50 border border-zinc-800 p-1 rounded-md">
          <TabsTrigger
            value="findings"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400"
          >
            <BarChart3 className="mr-2 h-4 w-4" />
            Findings Breakdown
          </TabsTrigger>
          <TabsTrigger
            value="reviews"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400"
          >
            <TrendingUp className="mr-2 h-4 w-4" />
            Review Health
          </TabsTrigger>
        </TabsList>

        {/* ── Findings Tab ───────────────────────────────────────── */}
        <TabsContent value="findings" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {/* Severity */}
            <Card className="bg-zinc-900/50 border-zinc-800 p-6 space-y-5">
              <h3 className="text-base font-semibold text-zinc-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                By Severity
              </h3>
              <div className="space-y-4">
                <SeverityBar
                  label="Critical"
                  count={sev.critical}
                  total={totalFindings}
                  color="bg-red-500/10 text-red-400"
                  icon={ShieldAlert}
                />
                <SeverityBar
                  label="High"
                  count={sev.high}
                  total={totalFindings}
                  color="bg-orange-500/10 text-orange-400"
                  icon={AlertTriangle}
                />
                <SeverityBar
                  label="Medium"
                  count={sev.medium}
                  total={totalFindings}
                  color="bg-amber-500/10 text-amber-400"
                  icon={Clock}
                />
                <SeverityBar
                  label="Low"
                  count={sev.low}
                  total={totalFindings}
                  color="bg-zinc-700/50 text-zinc-400"
                  icon={CheckCircle2}
                />
              </div>
            </Card>

            {/* Category */}
            <Card className="bg-zinc-900/50 border-zinc-800 p-6 space-y-5">
              <h3 className="text-base font-semibold text-zinc-200 flex items-center gap-2">
                <Bug className="h-4 w-4 text-purple-400" />
                By Category
              </h3>
              {data!.findings_by_category.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-40 text-center">
                  <Zap className="h-8 w-8 text-zinc-600 mb-3" />
                  <p className="text-sm text-zinc-500">
                    No findings recorded yet. Run a review to see data here.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {data!.findings_by_category.map((cat) => (
                    <SeverityBar
                      key={cat.name}
                      label={cat.name}
                      count={cat.count}
                      total={totalFindings}
                      color="bg-purple-500/10 text-purple-400"
                      icon={Lock}
                    />
                  ))}
                </div>
              )}
            </Card>
          </div>
        </TabsContent>

        {/* ── Review Health Tab ──────────────────────────────────── */}
        <TabsContent value="reviews" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {/* Pipeline Status */}
            <Card className="bg-zinc-900/50 border-zinc-800 p-6 space-y-5">
              <h3 className="text-base font-semibold text-zinc-200 flex items-center gap-2">
                <GitMerge className="h-4 w-4 text-blue-400" />
                Pipeline Status
              </h3>
              <div className="space-y-4">
                <SeverityBar
                  label="Completed"
                  count={rev.completed}
                  total={rev.total}
                  color="bg-emerald-500/10 text-emerald-400"
                  icon={CheckCircle2}
                />
                <SeverityBar
                  label="Running"
                  count={rev.running}
                  total={rev.total}
                  color="bg-blue-500/10 text-blue-400"
                  icon={TrendingUp}
                />
                <SeverityBar
                  label="Failed"
                  count={rev.failed}
                  total={rev.total}
                  color="bg-red-500/10 text-red-400"
                  icon={AlertTriangle}
                />
              </div>
            </Card>

            {/* Health summary */}
            <Card className="bg-zinc-900/50 border-zinc-800 p-6 flex flex-col gap-5">
              <h3 className="text-base font-semibold text-zinc-200 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-orange-400" />
                Health Summary
              </h3>
              <div className="grid grid-cols-2 gap-4 flex-1">
                {[
                  {
                    label: "Success Rate",
                    value: `${successRate}%`,
                    color: "text-emerald-400",
                  },
                  {
                    label: "Avg Findings",
                    value: data!.avg_findings_per_review.toFixed(1),
                    color: "text-amber-400",
                  },
                  {
                    label: "Critical Issues",
                    value: sev.critical,
                    color: "text-red-400",
                  },
                  {
                    label: "Active Repos",
                    value: data!.total_repositories,
                    color: "text-blue-400",
                  },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 p-4 flex flex-col items-center justify-center text-center"
                  >
                    <span className={`text-2xl font-bold ${item.color}`}>
                      {item.value}
                    </span>
                    <span className="text-xs text-zinc-500 mt-1">
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
