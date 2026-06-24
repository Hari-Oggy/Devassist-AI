"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Card } from "@/components/ui/card";
import { ReviewProgress } from "@/components/ReviewProgress";
import { FindingCard } from "@/components/FindingCard";
import { ArrowLeft, GitBranch, Code2, GitPullRequest, Calendar, Clock, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { readJson } from "@/lib/api";

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

  const fetchReviewData = () => {
    fetch(`/api/v3/reviews/${reviewId}`)
      .then(res => readJson<Review>(res))
      .then(data => {
        setReview(data);
        const s = data.status?.toLowerCase();
        if (s === "completed") {
          fetchFindings();
        } else {
          setLoading(false);
        }
      })
      .catch(console.error);
  };

  const fetchFindings = () => {
    fetch(`/api/v3/reviews/${reviewId}/findings`)
      .then(res => readJson<Finding[]>(res))
      .then(data => {
        setFindings(data);
        setLoading(false);
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchReviewData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500"></div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="p-8 text-center text-zinc-400">
        Review not found.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-8 space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <Link href="/reviews" className="inline-flex items-center text-sm text-zinc-400 hover:text-orange-400 transition-colors mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Reviews
      </Link>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-sm text-zinc-400">
          {review.provider === "github" ? <GitBranch className="h-4 w-4" /> : <Code2 className="h-4 w-4" />}
          <span>{review.repo_name}</span>
          <span>•</span>
          <GitPullRequest className="h-4 w-4" />
          <span>PR #{review.pr_number}</span>
        </div>
        <h1 className="text-3xl font-bold text-white tracking-tight">
          {review.pr_title || `Review #${review.id}`}
        </h1>
        <div className="flex items-center gap-4 text-sm text-zinc-500 mt-2">
          <span className="flex items-center gap-1.5"><Calendar className="h-3.5 w-3.5" /> {new Date(review.created_at).toLocaleDateString()}</span>
          <span className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> {new Date(review.created_at).toLocaleTimeString()}</span>
          <span className="font-mono bg-zinc-800/50 px-2 py-0.5 rounded">{review.commit_sha.substring(0, 7)}</span>
        </div>
      </div>

      <div className="grid gap-6 mt-8">
        {/* Pipeline Progress tracking via SSE */}
        {review.status?.toLowerCase() !== "completed" && review.status?.toLowerCase() !== "failed" && (
          <ReviewProgress 
            reviewId={reviewId} 
            initialStatus={review.status} 
            onComplete={() => {
              fetchReviewData(); // Refetch to get summary and findings
            }} 
          />
        )}

        {review.status?.toLowerCase() === "completed" && (
          <Card className="bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-2">Review Summary</h3>
            <p className="text-zinc-300 leading-relaxed whitespace-pre-wrap">
              {review.summary || "The review completed successfully but no summary was provided."}
            </p>
          </Card>
        )}

        {review.status?.toLowerCase() === "failed" && (
          <Card className="bg-red-950/20 border-red-900/50 p-6">
            <h3 className="text-lg font-semibold text-red-500 mb-2">Review Failed</h3>
            <p className="text-red-400/80 text-sm">
              An error occurred during the review pipeline execution. Please check the server logs.
            </p>
          </Card>
        )}

        {/* Findings List */}
        {review.status?.toLowerCase() === "completed" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mt-8 mb-4">
              <h2 className="text-xl font-semibold text-white">Findings ({findings.length})</h2>
            </div>
            
            {findings.length === 0 ? (
              <div className="text-center py-12 border border-zinc-800 border-dashed rounded-lg bg-zinc-900/20 text-zinc-500">
                <CheckCircle2 className="h-8 w-8 mx-auto mb-3 text-emerald-500/50" />
                <p>No critical issues found. The code looks good!</p>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {findings.map(finding => (
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
