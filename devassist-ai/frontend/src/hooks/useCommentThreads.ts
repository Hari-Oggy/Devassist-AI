import { useQuery } from "@tanstack/react-query";
import { fetchThreads } from "@/lib/api/threads";

export function useCommentThreads(reviewId: number, isCompleted: boolean = true) {
  return useQuery({
    queryKey: ["threads", reviewId],
    queryFn: () => fetchThreads(reviewId),
    enabled: isCompleted,
  });
}
