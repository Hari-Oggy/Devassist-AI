export interface LineRef {
  file_path: string;
  side: "additions" | "deletions";
  start_line: number;
  end_line: number;
}
export interface KeyChangeOut {
  id: number;
  content: string;
  line_refs: LineRef[];
}
export interface ChapterOut {
  id: number;
  order: number;
  title: string;
  summary: string;
  key_changes: KeyChangeOut[];
  file_paths: string[];
  finding_count: number;
}

export async function fetchChapters(reviewId: number): Promise<ChapterOut[]> {
  const res = await fetch(`/api/v3/reviews/${reviewId}/chapters`);
  if (!res.ok) throw new Error("Failed to fetch chapters");
  return res.json();
}
