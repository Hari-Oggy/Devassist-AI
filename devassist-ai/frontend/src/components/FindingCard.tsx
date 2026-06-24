import { AlertCircle, FileCode, CheckCircle, Lightbulb } from "lucide-react";
import { Card } from "@/components/ui/card";

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

export function FindingCard({ finding }: { finding: Finding }) {
  const getSeverityStyles = (severity: string) => {
    switch (severity.toLowerCase()) {
      case "error":
      case "critical":
        return {
          bg: "bg-red-500/10",
          border: "border-red-500/20",
          text: "text-red-400",
          icon: <AlertCircle className="h-4 w-4 text-red-500" />
        };
      case "warning":
        return {
          bg: "bg-amber-500/10",
          border: "border-amber-500/20",
          text: "text-amber-400",
          icon: <AlertCircle className="h-4 w-4 text-amber-500" />
        };
      case "suggestion":
      case "info":
        return {
          bg: "bg-blue-500/10",
          border: "border-blue-500/20",
          text: "text-blue-400",
          icon: <Lightbulb className="h-4 w-4 text-blue-500" />
        };
      default:
        return {
          bg: "bg-zinc-800",
          border: "border-zinc-700",
          text: "text-zinc-400",
          icon: <CheckCircle className="h-4 w-4 text-zinc-400" />
        };
    }
  };

  const styles = getSeverityStyles(finding.severity);

  return (
    <Card className={`border ${styles.border} bg-zinc-900/50 overflow-hidden`}>
      <div className={`px-4 py-2 flex items-center justify-between border-b ${styles.border} ${styles.bg}`}>
        <div className="flex items-center gap-2">
          {styles.icon}
          <span className={`text-xs font-semibold uppercase tracking-wider ${styles.text}`}>
            {finding.severity}
          </span>
          <span className="text-zinc-600 px-1">•</span>
          <span className="text-xs font-medium text-zinc-300 bg-zinc-800 px-2 py-0.5 rounded-full">
            {finding.category}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-zinc-400 bg-[#0a0a0a] px-3 py-1 rounded-md border border-zinc-800">
          <FileCode className="h-3.5 w-3.5" />
          <span>{finding.file_path}</span>
          <span className="text-zinc-600">:</span>
          <span className="text-orange-400">{finding.line_start}</span>
        </div>
      </div>
      
      <div className="p-4">
        <p className="text-zinc-300 text-sm leading-relaxed mb-4">
          {finding.message}
        </p>
        
        {finding.code_fix && (
          <div className="mt-4">
            <div className="flex items-center gap-2 mb-2">
              <Lightbulb className="h-3.5 w-3.5 text-emerald-500" />
              <span className="text-xs font-medium text-emerald-500">Suggested Fix</span>
            </div>
            <pre className="bg-[#0a0a0a] border border-emerald-500/20 rounded-md p-3 overflow-x-auto">
              <code className="text-xs font-mono text-zinc-300">
                {finding.code_fix}
              </code>
            </pre>
          </div>
        )}
      </div>
      
      <div className="px-4 py-2 bg-zinc-900/80 border-t border-zinc-800/50 flex justify-between items-center text-xs text-zinc-500">
        <span>Source: {finding.tool_source}</span>
        <button className="hover:text-white transition-colors underline decoration-zinc-700 underline-offset-4">
          Mark as resolved
        </button>
      </div>
    </Card>
  );
}
