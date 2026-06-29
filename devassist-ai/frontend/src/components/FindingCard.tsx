"use client";

import { useState } from "react";
import { AlertCircle, FileCode, CheckCircle, Lightbulb, EyeOff, Undo2, Loader2, ShieldCheck, Sparkles } from "lucide-react";

interface Finding {
  id: number;
  review_id?: number;
  file_path: string;
  line_start: number;
  severity: string;
  category: string;
  message: string;
  code_fix?: string | null;
  tool_source: string;
  is_suppressed: boolean;
}

function getSeverityStyles(severity: string) {
  switch (severity.toLowerCase()) {
    case "error":
    case "critical":
      return {
        bar: "bg-rose-500",
        badge: "bg-rose-500/10 border-rose-500/20 text-rose-400",
        icon: <AlertCircle className="h-4 w-4 text-rose-400" />,
      };
    case "high":
      return {
        bar: "bg-orange-500",
        badge: "bg-orange-500/10 border-orange-500/20 text-orange-400",
        icon: <AlertCircle className="h-4 w-4 text-orange-400" />,
      };
    case "warning":
    case "medium":
      return {
        bar: "bg-amber-500",
        badge: "bg-amber-500/10 border-amber-500/20 text-amber-400",
        icon: <AlertCircle className="h-4 w-4 text-amber-400" />,
      };
    case "suggestion":
    case "info":
    case "low":
      return {
        bar: "bg-cyan-500",
        badge: "bg-cyan-500/10 border-cyan-500/20 text-cyan-400",
        icon: <Lightbulb className="h-4 w-4 text-cyan-400" />,
      };
    default:
      return {
        bar: "bg-white/20",
        badge: "bg-white/5 border-white/10 text-white/40",
        icon: <CheckCircle className="h-4 w-4 text-white/40" />,
      };
  }
}

export function FindingCard({
  finding,
  reviewId,
}: {
  finding: Finding;
  reviewId?: number;
}) {
  const styles = getSeverityStyles(finding.severity);
  const [suppressed, setSuppressed] = useState(finding.is_suppressed);
  const [loading, setLoading] = useState(false);

  const resolvedReviewId = reviewId ?? finding.review_id;

  async function toggleSuppress() {
    if (!resolvedReviewId) return;
    setLoading(true);
    try {
      if (suppressed) {
        // Un-suppress
        await fetch(`/api/v3/reviews/${resolvedReviewId}/findings/${finding.id}/suppress`, {
          method: "DELETE",
        });
        setSuppressed(false);
      } else {
        // Suppress
        await fetch(`/api/v3/reviews/${resolvedReviewId}/findings/${finding.id}/suppress`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "Dismissed as false positive" }),
        });
        setSuppressed(true);
      }
    } catch {
      /* silently fail — log in prod */
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className={`rounded-2xl border bg-white/[0.02] overflow-hidden transition-all duration-200 hover:bg-white/[0.04] ${
        suppressed
          ? "border-white/[0.04] opacity-50"
          : finding.tool_source.toLowerCase() === "analyzer"
          ? "border-blue-500/20 hover:border-blue-500/40 shadow-[0_0_15px_rgba(59,130,246,0.05)]"
          : "border-white/[0.07] hover:border-white/[0.12]"
      }`}
    >
      {/* Severity color bar */}
      <div className={`h-0.5 w-full ${suppressed ? "bg-white/10" : styles.bar}`} />

      {/* Header */}
      <div className="px-5 py-4 flex items-center justify-between border-b border-white/[0.05] gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-bold uppercase tracking-wider ${
              suppressed ? "bg-white/5 border-white/10 text-white/30" : styles.badge
            }`}
          >
            {suppressed ? <EyeOff className="h-4 w-4" /> : styles.icon}
            {suppressed ? "suppressed" : finding.severity}
          </span>
          <span className="text-[12px] font-semibold text-white/50 bg-white/[0.04] border border-white/[0.07] px-2.5 py-1 rounded-lg">
            {finding.category}
          </span>
          {finding.tool_source.toLowerCase() === "analyzer" ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2.5 py-1 rounded-lg">
              <ShieldCheck className="h-3.5 w-3.5" /> Static Analysis
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2.5 py-1 rounded-lg">
              <Sparkles className="h-3.5 w-3.5" /> AI Review
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-violet-400 bg-violet-500/10 border border-violet-500/20 px-3 py-1.5 rounded-lg">
          <FileCode className="h-3.5 w-3.5" />
          <span className="text-white/50 truncate max-w-[200px]">{finding.file_path}</span>
          <span className="text-white/30">:</span>
          <span className="font-bold">{finding.line_start}</span>
        </div>
      </div>

      {/* Body */}
      <div className="p-5">
        <p className={`text-[14px] leading-relaxed font-medium ${suppressed ? "text-white/30" : "text-white/75"}`}>
          {finding.message}
        </p>

        {!suppressed && finding.code_fix && (
          <div className="mt-5 rounded-xl border border-emerald-500/15 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-emerald-500/15 bg-emerald-500/5">
              <Lightbulb className="h-4 w-4 text-emerald-400" />
              <span className="text-[12px] font-bold text-emerald-400">Suggested Fix</span>
            </div>
            <pre className="p-4 overflow-x-auto bg-black/20">
              <code className="text-[12px] font-mono text-white/60 leading-relaxed">
                {finding.code_fix}
              </code>
            </pre>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 bg-white/[0.015] border-t border-white/[0.05] flex justify-between items-center">
        <span className="text-[11px] text-white/30 font-medium">
          Source:{" "}
          <span className="text-white/50 font-semibold">{finding.tool_source}</span>
        </span>
        {resolvedReviewId ? (
          <button
            id={`suppress-finding-${finding.id}`}
            onClick={toggleSuppress}
            disabled={loading}
            className={`inline-flex items-center gap-1.5 text-[11px] font-bold transition-colors ${
              suppressed
                ? "text-emerald-400 hover:text-emerald-300"
                : "text-white/40 hover:text-rose-400"
            }`}
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : suppressed ? (
              <Undo2 className="h-3.5 w-3.5" />
            ) : (
              <EyeOff className="h-3.5 w-3.5" />
            )}
            {suppressed ? "Restore finding" : "Suppress"}
          </button>
        ) : (
          <span className="text-[11px] text-white/20">—</span>
        )}
      </div>
    </div>
  );
}
