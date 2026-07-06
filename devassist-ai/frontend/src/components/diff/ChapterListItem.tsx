import { ChapterOut } from "@/lib/api/chapters";
import { CheckCircle2, Circle } from "lucide-react";

export function ChapterListItem({
  chapter,
  selected,
  onClick,
}: {
  chapter: ChapterOut;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 flex items-start gap-3 border-b border-white/[0.05] transition-colors ${
        selected ? "bg-violet-500/10 border-l-2 border-l-violet-500" : "hover:bg-white/[0.02] border-l-2 border-l-transparent"
      }`}
    >
      <div className="mt-0.5 text-white/40">
        <Circle className="h-4 w-4" />
      </div>
      <div>
        <p className={`text-[14px] font-semibold ${selected ? "text-violet-400" : "text-white"}`}>
          {chapter.order}. {chapter.title}
        </p>
        <p className="text-[12px] text-white/50 line-clamp-2 mt-1">{chapter.summary}</p>
        <div className="flex gap-2 mt-2">
          {chapter.finding_count > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400">
              {chapter.finding_count} findings
            </span>
          )}
          {chapter.key_changes.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400">
              {chapter.key_changes.length} Qs
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
