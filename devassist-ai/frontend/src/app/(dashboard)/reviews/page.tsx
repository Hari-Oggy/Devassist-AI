"use client";

import { useEffect } from "react";
import { CheckCircle2, Clock, XCircle, Loader2, ArrowRight, GitBranch, Code2, ListTodo } from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { useDashboardStore, ReviewItem } from "@/lib/stores/dashboardStore";
import { PageHeader, GlassCard, LoadingSpinner, StatusBadge } from "@/components/ui/shared";

function getStatusIcon(status: string) {
  switch (status?.toLowerCase()) {
    case "completed": return <CheckCircle2 className="h-5 w-5 text-emerald-400" />;
    case "running": return <Loader2 className="h-5 w-5 text-violet-400 animate-spin" />;
    case "failed": return <XCircle className="h-5 w-5 text-rose-400" />;
    default: return <Clock className="h-5 w-5 text-white/30" />;
  }
}

function ReviewCard({ review }: { review: ReviewItem }) {
  return (
    <GlassCard noPad className="hover:border-violet-500/20 transition-all duration-300 group overflow-hidden">
      <div className="p-6 flex flex-col md:flex-row md:items-start justify-between gap-6">
        <div className="flex gap-4">
           {getStatusIcon(review.status)}
          {/* <div className="mt-1 shrink-0 p-2.5 bg-white/[0.04] rounded-xl border border-white/[0.07]">
           
          </div> */}
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-[12px] font-semibold text-white/40 flex items-center gap-1.5 bg-white/[0.04] px-2 py-1 rounded-lg border border-white/[0.06]">
                {review.provider === "github" ? <GitBranch className="h-3 w-3" /> : <Code2 className="h-3 w-3" />}
                {review.repo_name}
              </span>
              {review.pr_number && (
                <span className="text-[12px] font-bold text-white/40 bg-white/[0.04] px-2 py-1 rounded-lg border border-white/[0.06]">
                  PR #{review.pr_number}
                </span>
              )}
            </div>

            <h3 className="text-[15px] font-bold text-white mb-2 group-hover:text-violet-300 transition-colors">
              <Link href={`/reviews/${review.id}`}>
                {review.pr_title || `Review #${review.id}`}
              </Link>
            </h3>

            <p className="text-[13px] text-white/40 line-clamp-2 max-w-2xl leading-relaxed mb-4">
              {review.summary || "No summary available."}
            </p>

            <div className="flex items-center gap-3 flex-wrap">
              <StatusBadge status={review.status} />
              {review.commit_sha && (
                <span className="text-[11px] text-white/30 font-mono bg-white/[0.03] border border-white/[0.06] px-2 py-1 rounded-lg flex items-center gap-1.5">
                  <GitBranch className="h-3 w-3" />
                  {review.commit_sha.substring(0, 7)}
                </span>
              )}
              <span className="text-[12px] text-white/30 flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
              </span>
            </div>
          </div>
        </div>

        <div className="shrink-0 flex items-center justify-end md:justify-start">
          <Link href={`/reviews/${review.id}`}>
            <button className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-violet-500/20 bg-violet-500/5 text-[13px] font-bold text-violet-400 hover:bg-violet-500/10 hover:border-violet-500/30 transition-all duration-200">
              View Details
              <ArrowRight className="h-4 w-4" />
            </button>
          </Link>
        </div>
      </div>
    </GlassCard>
  );
}

export default function ReviewsPage() {
  const { reviews, loadingReviews, fetchReviews } = useDashboardStore();

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <PageHeader
        title="Reviews"
        subtitle="Monitor all automated PR reviews across your repositories."
      />

      {loadingReviews ? (
        <div className="flex items-center justify-center h-48">
          <LoadingSpinner />
        </div>
      ) : reviews.length === 0 ? (
        <GlassCard className="flex flex-col items-center justify-center py-20 text-center">
          <div className="h-20 w-20 rounded-3xl bg-white/[0.04] border border-white/[0.07] flex items-center justify-center mb-6">
            <ListTodo className="h-10 w-10 text-white/20" />
          </div>
          <h3 className="text-[20px] font-bold text-white mb-2">No reviews found</h3>
          <p className="text-white/40 max-w-sm text-[14px] leading-relaxed">
            When you open a PR on a connected repository, DevAssist AI will automatically review it and it will appear here.
          </p>
        </GlassCard>
      ) : (
        <div className="grid gap-4">
          {reviews.map((review) => (
            <ReviewCard key={review.id} review={review} />
          ))}
        </div>
      )}
    </div>
  );
}
