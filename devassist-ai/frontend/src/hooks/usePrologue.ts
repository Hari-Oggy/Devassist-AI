import { useQuery } from "@tanstack/react-query";
import { fetchPrologue } from "@/lib/api/prologue";

export function usePrologue(reviewId: number, isCompleted: boolean = true) {
  return useQuery({
    queryKey: ["prologue", reviewId],
    queryFn: () => fetchPrologue(reviewId),
    enabled: isCompleted,
  });
}
