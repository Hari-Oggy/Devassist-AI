"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ListTodo, ArrowRight, GitBranch, Code2, CheckCircle2, Clock, XCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
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

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v3/reviews")
      .then(res => readJson<Review[]>(res))
      .then(data => {
        setReviews(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case "completed":
        return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
      case "running":
        return <Loader2 className="h-5 w-5 text-amber-500 animate-spin" />;
      case "failed":
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Clock className="h-5 w-5 text-zinc-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case "completed":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "running":
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
      case "failed":
        return "bg-red-500/10 text-red-400 border-red-500/20";
      default:
        return "bg-zinc-800 text-zinc-400 border-zinc-700";
    }
  };

  return (
    <div className="mx-auto max-w-5xl p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-6">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Reviews</h1>
          <p className="text-zinc-400 mt-1">Monitor all automated PR reviews across your repositories.</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500"></div>
        </div>
      ) : reviews.length === 0 ? (
        <Card className="bg-zinc-900/30 border-zinc-800/60 p-12 flex flex-col items-center justify-center text-center">
          <div className="h-16 w-16 rounded-full bg-zinc-800/50 flex items-center justify-center mb-6">
            <ListTodo className="h-8 w-8 text-zinc-500" />
          </div>
          <h3 className="text-xl font-semibold text-white mb-2">No reviews found</h3>
          <p className="text-zinc-400 max-w-md mb-8">
            When you open a PR on a connected repository, DevAssist-AI will automatically review it and it will appear here.
          </p>
        </Card>
      ) : (
        <div className="grid gap-4">
          {reviews.map((review) => (
            <Card key={review.id} className="bg-zinc-900/50 border-zinc-800 p-0 overflow-hidden hover:border-zinc-700 transition-colors group">
              <div className="p-6 flex items-start justify-between">
                <div className="flex gap-4">
                  <div className="mt-1">
                    {getStatusIcon(review.status)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-zinc-400 flex items-center gap-1.5">
                        {review.provider === "github" ? <GitBranch className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
                        {review.repo_name}
                      </span>
                      <span className="text-zinc-600">•</span>
                      <span className="text-sm text-zinc-400">PR #{review.pr_number}</span>
                    </div>
                    
                    <h3 className="text-lg font-semibold text-white mb-2">
                      <Link href={`/reviews/${review.id}`} className="hover:text-orange-400 hover:underline">
                        {review.pr_title || `Review #${review.id}`}
                      </Link>
                    </h3>
                    
                    <p className="text-sm text-zinc-300 line-clamp-2 max-w-2xl">
                      {review.summary || "No summary available."}
                    </p>
                    
                    <div className="flex items-center gap-3 mt-4 text-xs">
                      <span className={`px-2 py-0.5 rounded-full border uppercase tracking-wider font-semibold ${getStatusBadge(review.status)}`}>
                        {review.status}
                      </span>
                      <span className="text-zinc-500 font-mono">
                        {review.commit_sha.substring(0, 7)}
                      </span>
                      <span className="text-zinc-500">
                        {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
                      </span>
                    </div>
                  </div>
                </div>
                
                <Link href={`/reviews/${review.id}`}>
                  <Button variant="ghost" className="text-zinc-400 hover:text-white">
                    Details <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
