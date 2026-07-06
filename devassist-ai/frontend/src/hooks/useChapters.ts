import { useQuery } from "@tanstack/react-query";
import { fetchChapters } from "@/lib/api/chapters";

export function useChapters(reviewId: number, isCompleted: boolean = true) {
  return useQuery({
    queryKey: ["chapters", reviewId],
    queryFn: () => fetchChapters(reviewId),
    enabled: isCompleted,
  });
}
