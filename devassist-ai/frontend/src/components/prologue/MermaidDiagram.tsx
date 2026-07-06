"use client";

import { useEffect, useRef, useId, useState } from "react";
import mermaid from "mermaid";

// Initialize mermaid once at module level
mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "loose",
  fontFamily: "ui-monospace, monospace",
});

export function MermaidDiagram({ source }: { source: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const reactId = useId();
  const [error, setError] = useState<string | null>(null);
  const [rendering, setRendering] = useState(true);

  useEffect(() => {
    if (!containerRef.current || !source) {
      setRendering(false);
      return;
    }

    // Clean the source: strip any markdown code fences the backend might have left
    let cleanSource = source.trim();
    
    // Remove ```mermaid ... ``` wrapping
    if (cleanSource.startsWith("```mermaid")) {
      cleanSource = cleanSource.slice("```mermaid".length);
    }
    if (cleanSource.startsWith("```")) {
      cleanSource = cleanSource.slice(3);
    }
    if (cleanSource.endsWith("```")) {
      cleanSource = cleanSource.slice(0, -3);
    }
    cleanSource = cleanSource.trim();

    if (!cleanSource) {
      setRendering(false);
      return;
    }

    // Use a stable, unique ID for this component instance
    const id = `mermaid-${reactId.replace(/:/g, "")}`;

    // Remove any stale SVG from a previous render (React Strict Mode double-invoke)
    const staleEl = document.getElementById(id);
    if (staleEl) {
      staleEl.remove();
    }

    let cancelled = false;

    mermaid
      .render(id, cleanSource)
      .then((result) => {
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = result.svg;
          setError(null);
          setRendering(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Failed to render mermaid diagram:", err);
          setError("Failed to render architecture diagram");
          setRendering(false);
          // Clean up any partial render artifacts mermaid left behind
          const partial = document.getElementById(id);
          if (partial) partial.remove();
        }
      });

    return () => {
      cancelled = true;
    };
  }, [source, reactId]);

  if (error) {
    return (
      <div className="text-red-400 text-sm p-4 border border-red-500/20 rounded-lg bg-red-500/10">
        <p className="font-semibold mb-1">⚠ Diagram Rendering Error</p>
        <p className="text-red-400/70 text-xs">{error}</p>
        <details className="mt-2">
          <summary className="text-red-400/50 text-xs cursor-pointer hover:text-red-400/80">Show raw diagram code</summary>
          <pre className="mt-2 text-[11px] text-red-400/60 overflow-x-auto whitespace-pre-wrap bg-red-500/5 p-2 rounded">{source}</pre>
        </details>
      </div>
    );
  }

  return (
    <div className="relative">
      {rendering && (
        <div className="flex items-center justify-center py-6">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500/20 border-t-violet-500" />
        </div>
      )}
      <div
        ref={containerRef}
        className="mermaid flex justify-center py-4 [&_svg]:max-w-full"
      />
    </div>
  );
}
