"use client";

import { usePrologue } from "@/hooks/usePrologue";
import { MermaidDiagram } from "./MermaidDiagram";
import { FocusAreaBadge } from "./FocusAreaBadge";

export function ProloguePanel({ reviewId }: { reviewId: number }) {
  const { data: prologue, isLoading, error } = usePrologue(reviewId);

  if (isLoading) return <div className="p-6 text-white/40">Loading prologue...</div>;
  if (error) return <div className="p-6 text-red-400/60">Failed to load prologue.</div>;
  if (!prologue) return null;

  // Guard against empty/fallback prologue
  const isFallback = prologue.motivation === "Could not determine motivation.";

  return (
    <section className="border-b border-white/[0.06] p-6 space-y-6 bg-white/[0.01]">
      <h2 className="text-xl font-bold text-white">Review Overview</h2>
      
      {isFallback && (
        <div className="text-amber-400/70 text-[13px] px-3 py-2 bg-amber-500/5 border border-amber-500/15 rounded-lg">
          ⚠ Prologue synthesis encountered an issue. Showing fallback data. Re-trigger the review for a full analysis.
        </div>
      )}

      <div className="space-y-4">
        {prologue.motivation && (
          <div>
            <h3 className="text-[13px] font-semibold text-white/40 uppercase tracking-wider mb-1">Motivation</h3>
            <p className="text-[14px] text-white/80 leading-relaxed">{prologue.motivation}</p>
          </div>
        )}
        
        {prologue.outcome && (
          <div>
            <h3 className="text-[13px] font-semibold text-white/40 uppercase tracking-wider mb-1">Outcome</h3>
            <p className="text-[14px] text-white/80 leading-relaxed">{prologue.outcome}</p>
          </div>
        )}
      </div>

      {prologue.diagram && (
        <div className="my-6 p-4 bg-black/20 rounded-xl border border-white/[0.05]">
          <h3 className="text-[13px] font-semibold text-white/40 uppercase tracking-wider mb-3">Architecture Diagram</h3>
          <MermaidDiagram source={prologue.diagram} />
        </div>
      )}

      {prologue.focus_areas && prologue.focus_areas.length > 0 && (
        <div>
          <h3 className="text-[13px] font-semibold text-white/40 uppercase tracking-wider mb-3">Focus Areas</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {prologue.focus_areas.map((area, i) => (
              <FocusAreaBadge key={i} area={area} />
            ))}
          </div>
        </div>
      )}

      {prologue.complexity && (
        <div className="flex items-center gap-2 mt-4 text-[13px]">
          <span className="font-semibold text-white/40">Complexity:</span>
          <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/80 font-medium capitalize">
            {prologue.complexity.level}
          </span>
          <span className="text-white/60 ml-2">{prologue.complexity.reasoning}</span>
        </div>
      )}
    </section>
  );
}
