"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ReviewProgress } from "@/components/ReviewProgress";
import { FindingCard } from "@/components/FindingCard";
import {
  ArrowLeft,
  GitBranch,
  Code2,
  GitPullRequest,
  Calendar,
  Clock,
  CheckCircle2,
  FileCode2,
  Activity,
  ChevronRight,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { readJson } from "@/lib/api";
import { GlassCard, LoadingSpinner, StatusBadge } from "@/components/ui/shared";

interface Review {
  id: number;
  status: string;
  summary: string;
  commit_sha: string;
  created_at: string;
  pr_title: string;
  pr_number: number;
  repo_name: string;
  provider: string;
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

export default function ReviewDetailPage() {
  const params = useParams();
  const reviewId = parseInt(params.id as string, 10);

  const [review, setReview] = useState<Review | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);

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
            {review.provider === "github" ? <GitBranch className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
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
            label: "Files Changed",
            value: "—",
            icon: <FileCode2 className="h-5 w-5" />,
            accent: "violet",
            bg: "bg-violet-500/10",
            border: "border-violet-500/20",
            text: "text-violet-400",
          },
          {
            label: "Lines Edited",
            value: "—",
            icon: <Activity className="h-5 w-5" />,
            accent: "cyan",
            bg: "bg-cyan-500/10",
            border: "border-cyan-500/20",
            text: "text-cyan-400",
          },
          {
            label: "Findings",
            value: findings.length,
            icon: <ShieldAlert className="h-5 w-5" />,
            accent: findings.length > 0 ? "rose" : "emerald",
            bg: findings.length > 0 ? "bg-rose-500/10" : "bg-emerald-500/10",
            border: findings.length > 0 ? "border-rose-500/20" : "border-emerald-500/20",
            text: findings.length > 0 ? "text-rose-400" : "text-emerald-400",
          },
        ].map((stat) => (
          <GlassCard key={stat.label} className="flex items-center gap-4">
            <div className={`p-3 rounded-xl border ${stat.bg} ${stat.border} ${stat.text} shrink-0`}>
              {stat.icon}
            </div>
            <div>
              <p className="text-[12px] font-medium text-white/40">{stat.label}</p>
              <p className="text-[20px] font-bold text-white leading-none mt-0.5">{stat.value}</p>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Content area */}
      <div className="space-y-6">
        {/* Pipeline Progress (SSE) */}
        {review.status?.toLowerCase() !== "completed" &&
          review.status?.toLowerCase() !== "failed" && (
            <ReviewProgress
              reviewId={reviewId}
              initialStatus={review.status}
              onComplete={() => fetchReviewData()}
            />
          )}

        {/* Summary */}
        {review.status?.toLowerCase() === "completed" && (
          <GlassCard className="relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-full bg-gradient-to-l from-violet-500/5 to-transparent pointer-events-none" />
            <h3 className="text-[15px] font-bold text-white mb-4">Review Summary</h3>
            <p className="text-[14px] text-white/60 leading-relaxed whitespace-pre-wrap">
              {review.summary || "The review completed successfully but no summary was provided."}
            </p>
          </GlassCard>
        )}

        {/* Failed state */}
        {review.status?.toLowerCase() === "failed" && (
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

        {/* Findings List */}
        {review.status?.toLowerCase() === "completed" && (
          <div className="space-y-5">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-4">
              <h2 className="text-[17px] font-bold text-white">
                Findings{" "}
                <span className="text-white/30 font-normal text-[15px]">({findings.length})</span>
              </h2>
            </div>

            {findings.length === 0 ? (
              <div className="text-center py-16 rounded-2xl border border-white/[0.07] border-dashed bg-white/[0.01]">
                <CheckCircle2 className="h-12 w-12 mx-auto mb-4 text-emerald-500/60" />
                <p className="font-bold text-white text-[16px]">No issues found!</p>
                <p className="text-[13px] text-white/40 mt-1">The code looks great and follows best practices.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-5">
                {findings.map((finding) => (
                  <FindingCard key={finding.id} finding={finding} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
