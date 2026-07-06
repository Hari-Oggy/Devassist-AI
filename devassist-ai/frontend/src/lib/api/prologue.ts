export interface PrologueOut {
  motivation?: string;
  outcome?: string;
  diagram?: string;
  focus_areas: Array<{
    type: string;
    severity: string;
    title: string;
    description: string;
  }>;
  complexity: {
    level: string;
    reasoning: string;
  };
}

export async function 
fetchPrologue(reviewId: number): Promise<PrologueOut> {
  const res = await fetch(`/api/v3/reviews/${reviewId}/prologue`);
  if (res.status === 404) return null as any;
  if (!res.ok) throw new Error("Failed to fetch prologue");
  return res.json();
}
