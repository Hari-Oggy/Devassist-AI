"use client";

import { useChapters } from "@/hooks/useChapters";
import { ChapterListItem } from "./ChapterListItem";

export function ChapterList({
  reviewId,
  selectedChapterId,
  onSelect,
}: {
  reviewId: number;
  selectedChapterId: number | null;
  onSelect: (id: number) => void;
}) {
  const { data: chapters, isLoading } = useChapters(reviewId);

  if (isLoading) return <aside className="w-72 border-r border-white/10 p-4">Loading chapters...</aside>;
  if (!chapters || chapters.length === 0) return null;

  return (
    <aside className="w-72 border-r border-white/[0.06] bg-[#0d1117] flex flex-col h-full shrink-0">
      <div className="p-4 border-b border-white/[0.06]">
        <h3 className="font-semibold text-white/80">Chapters</h3>
      </div>
      <div className="overflow-y-auto flex-1">
        {chapters.map((c) => (
          <ChapterListItem
            key={c.id}
            chapter={c}
            selected={c.id === selectedChapterId}
            onClick={() => onSelect(c.id)}
          />
        ))}
      </div>
    </aside>
  );
}
