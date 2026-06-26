import { AlertCircle, FileCode, CheckCircle, Lightbulb } from "lucide-react";

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

export function FindingCard({ finding }: { finding: Finding }) {
  const styles = getSeverityStyles(finding.severity);

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] overflow-hidden transition-all duration-200 hover:border-white/[0.12] hover:bg-white/[0.04]">
      {/* Severity color bar */}
      <div className={`h-0.5 w-full ${styles.bar}`} />

      {/* Header */}
      <div className="px-5 py-4 flex items-center justify-between border-b border-white/[0.05] gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-bold uppercase tracking-wider ${styles.badge}`}
          >
            {styles.icon}
            {finding.severity}
          </span>
          <span className="text-[12px] font-semibold text-white/50 bg-white/[0.04] border border-white/[0.07] px-2.5 py-1 rounded-lg">
            {finding.category}
          </span>
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
        <p className="text-[14px] text-white/75 leading-relaxed font-medium">
          {finding.message}
        </p>

        {finding.code_fix && (
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
        <button className="text-[11px] font-bold text-violet-400 hover:text-violet-300 transition-colors">
          Mark as resolved →
        </button>
      </div>
    </div>
  );
}
