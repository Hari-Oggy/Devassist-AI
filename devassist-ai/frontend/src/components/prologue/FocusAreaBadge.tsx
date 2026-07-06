import { ShieldAlert, AlertTriangle, Info, Zap } from "lucide-react";

type Severity = "critical" | "high" | "medium" | "low" | string;

interface FocusArea {
  severity?: Severity;
  title: string;
  description?: string;
}

export function FocusAreaBadge({ area }: { area: FocusArea }) {
  let Icon = Info;
  let color = "text-blue-400 bg-blue-500/10 border-blue-500/20";
  
  if (area.severity === "critical") {
    Icon = ShieldAlert;
    color = "text-rose-400 bg-rose-500/10 border-rose-500/20";
  } else if (area.severity === "high") {
    Icon = AlertTriangle;
    color = "text-orange-400 bg-orange-500/10 border-orange-500/20";
  } else if (area.severity === "medium") {
    Icon = Zap;
    color = "text-amber-400 bg-amber-500/10 border-amber-500/20";
  }

  return (
    <div className={`flex items-start gap-3 p-3 rounded-xl border ${color}`}>
      <Icon className="h-5 w-5 shrink-0 mt-0.5" />
      <div>
        <p className="font-semibold text-[13px]">{area.title}</p>
        <p className="opacity-80 text-[12px] leading-snug">{area.description}</p>
      </div>
    </div>
  );
}
