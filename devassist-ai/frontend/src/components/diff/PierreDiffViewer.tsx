"use client";

import { ChapterList } from "./ChapterList";
import { PatchDiff, type SelectedLineRange } from "@pierre/diffs/react";
import { useState, useEffect } from "react";

export function PierreDiffViewer({ reviewId, chapterId, onSelectChapter }: { reviewId: number, chapterId: number | null, onSelectChapter: (id: number) => void }) {
  const [diff, setDiff] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!chapterId) {
      setDiff(null);
      return;
    }
    
    setLoading(true);
    fetch(`/api/v3/reviews/${reviewId}/chapters/${chapterId}/diff`)
      .then(res => res.json())
      .then(data => {
        setDiff(data.diff);
      })
      .catch(err => console.error("Failed to fetch diff:", err))
      .finally(() => setLoading(false));
  }, [reviewId, chapterId]);
  return (
    <div className="flex bg-[#0d1117] min-h-[600px] border border-white/10 rounded-xl overflow-hidden">
      <ChapterList reviewId={reviewId} selectedChapterId={chapterId} onSelect={onSelectChapter} />
      <div className="flex-1 p-6 text-white/60 bg-black/20 overflow-y-auto">
        {!chapterId ? (
          <div className="h-full flex items-center justify-center">
            <p>Select a chapter from the sidebar to view diffs.</p>
          </div>
        ) : loading ? (
          <div className="h-full flex items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-500/20 border-t-emerald-500" />
          </div>
        ) : diff ? (
          <div>
            <h3 className="text-xl font-bold text-white mb-4">Chapter {chapterId} Code Diff</h3>
            <div className="flex flex-col gap-6">
              {diff.split(/^(?=--- a\/|diff --git )/m).filter(chunk => chunk.trim().length > 0).map((chunk, idx) => (
                <div key={idx} className="rounded-lg font-mono text-[13px] bg-white/[0.02] border border-white/10 overflow-hidden">
                  <PatchDiff
                    patch={chunk}
                    onLineSelection={(sel: SelectedLineRange | null) => console.log("Selected line:", sel)}
                  />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <p>No diff available for this chapter.</p>
          </div>
        )}
      </div>
    </div>
  );
}
