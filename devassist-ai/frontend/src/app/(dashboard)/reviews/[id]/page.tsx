"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ReviewProgress } from "@/components/ReviewProgress";
import { FindingCard } from "@/components/FindingCard";
import { DocumentationTab } from "@/components/DocumentationTab";
import { BlastRadiusGraph } from "@/components/BlastRadiusGraph";
import {
  ArrowLeft,
  GitBranch,
  Code2,
  GitPullRequest,
  Calendar,
  Clock,
  FileCode2,
  Activity,
  ShieldAlert,
  XCircle,
  CheckCircle2,
  ChevronRight,
  Network,
  AlertTriangle,
  FileWarning,
} from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ProloguePanel } from "@/components/prologue/ProloguePanel";
import { PierreDiffViewer } from "@/components/diff/PierreDiffViewer";
import { BookOpen, Layers } from "lucide-react";

// ── Shared UI primitives ────────────────────────────────────────────────

function GlassCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-white/[0.07] bg-white/[0.03] backdrop-blur-sm p-6 ${className}`}
    >
      {children}
    </div>
  );
}

function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" };
  return (
    <div
      className={`${sizes[size]} animate-spin rounded-full border-2 border-violet-500/20 border-t-violet-500`}
    />
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = status?.toLowerCase();
  const map: Record<string, string> = {
    completed: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400",
    running: "bg-violet-500/10 border-violet-500/20 text-violet-400",
    pending: "bg-amber-500/10 border-amber-500/20 text-amber-400",
    failed: "bg-rose-500/10 border-rose-500/20 text-rose-400",
    skipped: "bg-white/5 border-white/10 text-white/30",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-[11px] font-bold uppercase tracking-wider ${
        map[s] ?? map.skipped
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

// ── Tabs ────────────────────────────────────────────────────────────────

type Tab = "prologue" | "chapters" | "findings" | "impact" | "documentation";

// ── Types ───────────────────────────────────────────────────────────────

interface Review {
  id: number;
  status: string;
  summary?: string;
  commit_sha?: string;
  created_at: string;
  completed_at?: string;
  pr_title?: string;
  pr_number?: number;
  repo_name?: string;
  provider?: string;
  total_findings?: number;
}

interface Finding {
  id: number;
  file_path: string;
  line_start: number;
  severity: string;
  category: string;
  message: string;
  code_fix?: string | null;
  tool_source: string;
  is_suppressed: boolean;
}

interface ImpactReport {
  affected_files: string[];
  blast_radius: number;
  changed_files: string[];
  callers: Record<string, string[]>;
}

// ── readJson helper ─────────────────────────────────────────────────────

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Impact Analysis Tab ─────────────────────────────────────────────────

function ImpactTab({
  reviewId,
  isCompleted,
}: {
  reviewId: number;
  isCompleted: boolean;
}) {
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!isCompleted) {
      setLoading(false);
      return;
    }
    fetch(`/api/v3/reviews/${reviewId}/impact`)
      .then((res) => readJson<{ affected_files: string[]; blast_radius: number; changed_files: string[]; callers: Record<string, string[]> }>(res))
      .then((data) => {
        setImpact(data);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [reviewId, isCompleted]);

  if (!isCompleted) {
    return (
      <GlassCard className="text-center py-12">
        <Network className="h-12 w-12 mx-auto mb-4 text-violet-400/40" />
        <p className="text-white/40 font-medium">
          Impact analysis will be available once the review completes.
        </p>
      </GlassCard>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <GlassCard className="text-center py-12">
        <XCircle className="h-10 w-10 mx-auto mb-4 text-rose-400/50" />
        <p className="text-white/40 font-medium">Could not load impact data.</p>
      </GlassCard>
    );
  }

  const affectedFiles = impact?.affected_files ?? [];
  const changedFiles = impact?.changed_files ?? [];
  const callers = impact?.callers ?? {};
  const blastRadius = impact?.blast_radius ?? 0;

  const hasData =
    affectedFiles.length > 0 || changedFiles.length > 0 || Object.keys(callers).length > 0;

  if (!hasData) {
    return (
      <GlassCard className="text-center py-12">
        <CheckCircle2 className="h-12 w-12 mx-auto mb-4 text-emerald-500/50" />
        <p className="font-bold text-white text-[16px]">No blast radius detected</p>
        <p className="text-[13px] text-white/40 mt-1">
          The changed files don&apos;t have indirect effects on other parts of the codebase.
        </p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary card */}
      <div className="grid grid-cols-2 gap-5">
        <GlassCard className="flex items-center gap-4">
          <div className="p-3 rounded-xl border bg-orange-500/10 border-orange-500/20 text-orange-400 shrink-0">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <p className="text-[12px] font-medium text-white/40">Blast Radius</p>
            <p className="text-[20px] font-bold text-white leading-none mt-0.5">
              {blastRadius || affectedFiles.length}
              <span className="text-[13px] font-normal text-white/40 ml-1">files</span>
            </p>
          </div>
        </GlassCard>
        <GlassCard className="flex items-center gap-4">
          <div className="p-3 rounded-xl border bg-violet-500/10 border-violet-500/20 text-violet-400 shrink-0">
            <FileWarning className="h-5 w-5" />
          </div>
          <div>
            <p className="text-[12px] font-medium text-white/40">Directly Changed</p>
            <p className="text-[20px] font-bold text-white leading-none mt-0.5">
              {changedFiles.length}
              <span className="text-[13px] font-normal text-white/40 ml-1">files</span>
            </p>
          </div>
        </GlassCard>
      </div>

      {/* Interactive ReactFlow Graph */}
      <BlastRadiusGraph 
        changedFiles={changedFiles} 
        affectedFiles={affectedFiles} 
        callers={callers} 
      />

      {/* Affected files */}
      {affectedFiles.length > 0 && (
        <GlassCard>
          <div className="flex items-center gap-3 mb-5">
            <div className="p-2.5 rounded-xl bg-orange-500/10 border border-orange-500/20">
              <AlertTriangle className="h-4 w-4 text-orange-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white">Indirectly Affected Files</h3>
              <p className="text-[12px] text-white/40 mt-0.5">
                These files may break if the changed code is incorrect
              </p>
            </div>
          </div>
          <ul className="space-y-2">
            {affectedFiles.map((file) => (
              <li
                key={file}
                className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.02] border border-white/[0.05] hover:border-orange-500/20 hover:bg-orange-500/5 transition-all duration-150"
              >
                <FileCode2 className="h-4 w-4 text-orange-400/60 shrink-0" />
                <code className="text-[13px] font-mono text-white/70">{file}</code>
              </li>
            ))}
          </ul>
        </GlassCard>
      )}

      {/* Callers / symbol dependencies */}
      {Object.keys(callers).length > 0 && (
        <GlassCard>
          <div className="flex items-center gap-3 mb-5">
            <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
              <Network className="h-4 w-4 text-violet-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white">Symbol Dependency Map</h3>
              <p className="text-[12px] text-white/40 mt-0.5">
                Functions / classes that depend on your changed symbols
              </p>
            </div>
          </div>
          <div className="space-y-4">
            {Object.entries(callers).map(([symbol, callerList]) => (
              <div
                key={symbol}
                className="rounded-xl border border-white/[0.06] bg-white/[0.01] overflow-hidden"
              >
                <div className="px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
                  <code className="text-[13px] font-mono font-bold text-violet-300">{symbol}</code>
                </div>
                <ul className="p-3 space-y-1.5">
                  {(callerList as string[]).map((caller) => (
                    <li key={caller} className="flex items-center gap-2">
                      <ChevronRight className="h-3.5 w-3.5 text-white/20 shrink-0" />
                      <code className="text-[12px] font-mono text-white/55">{caller}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────

export default function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const reviewId = parseInt(id, 10);

  const [review, setReview] = useState<Review | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("prologue");
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);

  const fetchFindings = () => {
    fetch(`/api/v3/reviews/${reviewId}/findings`)
      .then((res) => readJson<Finding[]>(res))
      .then((data) => {
        setFindings(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  const fetchReviewData = () => {
    fetch(`/api/v3/reviews/${reviewId}`)
      .then((res) => readJson<Review>(res))
      .then((data) => {
        setReview(data);
        const s = data.status?.toLowerCase();
        if (s === "completed") {
          fetchFindings();
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchReviewData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!review) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
        <div className="text-center">
          <XCircle className="h-12 w-12 text-rose-500/50 mx-auto mb-3" />
          <p className="text-white/40 font-medium">Review not found.</p>
        </div>
      </div>
    );
  }

  const isCompleted = review.status?.toLowerCase() === "completed";
  const isFailed = review.status?.toLowerCase() === "failed";

  return (
    <div className="mx-auto max-w-[1200px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-[13px] text-white/40 font-medium">
        <Link href="/reviews" className="flex items-center gap-1.5 hover:text-white/70 transition-colors">
          <ArrowLeft className="h-4 w-4" />
          Reviews
        </Link>
        <ChevronRight className="h-3.5 w-3.5 opacity-40" />
        <span className="text-white/70 truncate max-w-md">
          {review.pr_title || `Review #${review.id}`}
        </span>
      </div>

      {/* Header */}
      <div className="space-y-4">
        <div className="flex items-center gap-3 flex-wrap text-[12px] font-semibold text-white/40">
          <span className="flex items-center gap-1.5 bg-white/[0.04] border border-white/[0.07] px-3 py-1.5 rounded-lg text-white/60">
            {review.provider === "github" ? (
              <GitBranch className="h-3.5 w-3.5" />
            ) : (
              <Code2 className="h-3.5 w-3.5" />
            )}
            {review.repo_name}
          </span>
          <span className="flex items-center gap-1.5 bg-white/[0.04] border border-white/[0.07] px-3 py-1.5 rounded-lg">
            <GitPullRequest className="h-3.5 w-3.5" />
            PR #{review.pr_number}
          </span>
        </div>

        <h1 className="text-[1.75rem] font-bold text-white tracking-tight">
          {review.pr_title || `Review #${review.id}`}
        </h1>

        <div className="flex flex-wrap items-center gap-3 text-[12px] font-medium">
          <StatusBadge status={review.status} />
          <span className="flex items-center gap-1.5 text-white/35 bg-white/[0.03] border border-white/[0.06] px-2.5 py-1 rounded-lg">
            <Calendar className="h-3.5 w-3.5" />
            {new Date(review.created_at).toLocaleDateString("en-GB", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </span>
          <span className="flex items-center gap-1.5 text-white/35 bg-white/[0.03] border border-white/[0.06] px-2.5 py-1 rounded-lg">
            <Clock className="h-3.5 w-3.5" />
            {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
          </span>
          {review.commit_sha && (
            <span className="font-mono flex items-center gap-1.5 text-violet-400 bg-violet-500/10 border border-violet-500/20 px-2.5 py-1 rounded-lg">
              <GitBranch className="h-3.5 w-3.5" />
              {review.commit_sha.substring(0, 7)}
            </span>
          )}
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-5">
        {[
          {
            label: "Total Findings",
            value: review.total_findings ?? findings.length,
            icon: <ShieldAlert className="h-5 w-5" />,
            bg: findings.length > 0 ? "bg-rose-500/10" : "bg-emerald-500/10",
            border: findings.length > 0 ? "border-rose-500/20" : "border-emerald-500/20",
            text: findings.length > 0 ? "text-rose-400" : "text-emerald-400",
          },
          {
            label: "Active Findings",
            value: findings.filter((f) => !f.is_suppressed).length,
            icon: <AlertTriangle className="h-5 w-5" />,
            bg: "bg-amber-500/10",
            border: "border-amber-500/20",
            text: "text-amber-400",
          },
          {
            label: "Status",
            value: review.status,
            icon: <Activity className="h-5 w-5" />,
            bg: isCompleted ? "bg-emerald-500/10" : isFailed ? "bg-rose-500/10" : "bg-violet-500/10",
            border: isCompleted ? "border-emerald-500/20" : isFailed ? "border-rose-500/20" : "border-violet-500/20",
            text: isCompleted ? "text-emerald-400" : isFailed ? "text-rose-400" : "text-violet-400",
          },
        ].map((stat) => (
          <GlassCard key={stat.label} className="flex items-center gap-4">
            <div className={`p-3 rounded-xl border ${stat.bg} ${stat.border} ${stat.text} shrink-0`}>
              {stat.icon}
            </div>
            <div>
              <p className="text-[12px] font-medium text-white/40">{stat.label}</p>
              <p className="text-[20px] font-bold text-white leading-none mt-0.5 capitalize">
                {stat.value}
              </p>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Content area */}
      <div className="space-y-6">
        {/* Pipeline Progress (SSE) */}
        {!isCompleted && !isFailed && (
          <ReviewProgress
            reviewId={reviewId}
            initialStatus={review.status}
            onComplete={() => fetchReviewData()}
          />
        )}

        {/* Summary */}
        {isCompleted && (
          <GlassCard className="relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-full bg-gradient-to-l from-violet-500/5 to-transparent pointer-events-none" />
            <h3 className="text-[15px] font-bold text-white mb-4">Review Summary</h3>
            <p className="text-[14px] text-white/60 leading-relaxed whitespace-pre-wrap">
              {review.summary || "The review completed successfully but no summary was provided."}
            </p>
          </GlassCard>
        )}

        {/* Failed state */}
        {isFailed && (
          <div className="flex items-start gap-4 p-6 rounded-2xl bg-rose-500/5 border border-rose-500/20">
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 shrink-0">
              <XCircle className="h-6 w-6 text-rose-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-rose-400 mb-1">Review Failed</h3>
              <p className="text-[13px] text-rose-400/60">
                An error occurred during the review pipeline execution. Please check the server logs.
              </p>
            </div>
          </div>
        )}

        {/* Tabs — only shown after completion */}
        {isCompleted && (
          <div className="space-y-6">
            {/* Tab header */}
            <div className="flex gap-1 border-b border-white/[0.06]">
              {(
                [
                  { id: "prologue", label: "Prologue", icon: <BookOpen className="h-4 w-4" /> },
                  { id: "chapters", label: "Chapters", icon: <Layers className="h-4 w-4" /> },
                  { id: "findings", label: `Findings (${findings.length})`, icon: <ShieldAlert className="h-4 w-4" /> },
                  { id: "impact", label: "Impact Analysis", icon: <Network className="h-4 w-4" /> },
                  { id: "documentation", label: "Documentation", icon: <FileCode2 className="h-4 w-4" /> },
                ] as { id: Tab; label: string; icon: React.ReactNode }[]
              ).map((tab) => (
                <button
                  key={tab.id}
                  id={`tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3 text-[13px] font-semibold border-b-2 -mb-px transition-all duration-150 ${
                    activeTab === tab.id
                      ? "border-violet-500 text-violet-400"
                      : "border-transparent text-white/40 hover:text-white/70"
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {activeTab === "prologue" && (
              <ProloguePanel reviewId={reviewId} />
            )}

            {activeTab === "chapters" && (
              <PierreDiffViewer 
                reviewId={reviewId} 
                chapterId={selectedChapterId} 
                onSelectChapter={setSelectedChapterId} 
              />
            )}

            {activeTab === "findings" && (
              <div className="space-y-5">
                {findings.length === 0 ? (
                  <div className="text-center py-16 rounded-2xl border border-white/[0.07] border-dashed bg-white/[0.01]">
                    <CheckCircle2 className="h-12 w-12 mx-auto mb-4 text-emerald-500/60" />
                    <p className="font-bold text-white text-[16px]">No issues found!</p>
                    <p className="text-[13px] text-white/40 mt-1">
                      The code looks great and follows best practices.
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-5">
                    {findings.map((finding) => (
                      <FindingCard
                        key={finding.id}
                        finding={finding}
                        reviewId={reviewId}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === "impact" && (
              <ImpactTab reviewId={reviewId} isCompleted={isCompleted} />
            )}

            {activeTab === "documentation" && (
              <DocumentationTab reviewId={reviewId} isCompleted={isCompleted} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
