export interface CommentThreadOut {
  id: number;
  file_path: string;
  line_start: number;
  line_end: number;
  side: "additions" | "deletions";
  status: "local" | "pending" | "submitted";
  resolved: boolean;
  comments: CommentOut[];
}

export interface CommentOut {
  id: number;
  author: string;
  body: string;
  is_bot: boolean;
  created_at?: string;
}

export async function fetchThreads(reviewId: number): Promise<CommentThreadOut[]> {
  const res = await fetch(`/api/v3/reviews/${reviewId}/threads`);
  if (!res.ok) throw new Error("Failed to fetch threads");
  return res.json();
}
