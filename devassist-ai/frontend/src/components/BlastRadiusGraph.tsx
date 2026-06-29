"use client";

import React, { useMemo } from "react";
import ReactFlow, { Background, Controls, Node, Edge, MarkerType, Panel } from "reactflow";
import "reactflow/dist/style.css";
import { AlertTriangle, FileCode2, Network } from "lucide-react";

interface BlastRadiusGraphProps {
  changedFiles: string[];
  affectedFiles: string[];
  callers: Record<string, string[]>;
}

export function BlastRadiusGraph({
  changedFiles,
  affectedFiles,
  callers,
}: BlastRadiusGraphProps) {
  // Convert impact data into nodes and edges for React Flow
  const { nodes, edges } = useMemo(() => {
    const initialNodes: Node[] = [];
    const initialEdges: Edge[] = [];
    
    let yOffset = 0;
    
    // Create nodes for changed files (Roots)
    changedFiles.forEach((file, index) => {
      initialNodes.push({
        id: file,
        position: { x: 50, y: 50 + index * 100 },
        data: { 
          label: (
            <div className="flex items-center gap-2 px-2 py-1">
              <FileCode2 className="h-4 w-4 text-rose-400" />
              <span className="font-mono text-xs font-bold text-rose-100">{file}</span>
            </div>
          )
        },
        style: {
          background: "rgba(244, 63, 94, 0.1)",
          border: "1px solid rgba(244, 63, 94, 0.3)",
          borderRadius: "8px",
          color: "white",
        },
      });
      yOffset = Math.max(yOffset, 50 + index * 100);
    });

    // Create nodes for affected files
    affectedFiles.forEach((file, index) => {
      // Don't duplicate nodes if a file is both changed and affected
      if (!initialNodes.find((n) => n.id === file)) {
        initialNodes.push({
          id: file,
          position: { x: 400, y: 50 + index * 100 },
          data: { 
            label: (
              <div className="flex items-center gap-2 px-2 py-1">
                <AlertTriangle className="h-4 w-4 text-orange-400" />
                <span className="font-mono text-xs font-semibold text-orange-100">{file}</span>
              </div>
            )
          },
          style: {
            background: "rgba(249, 115, 22, 0.1)",
            border: "1px solid rgba(249, 115, 22, 0.3)",
            borderRadius: "8px",
            color: "white",
          },
        });
      }
    });

    // Create edges based on callers / dependencies
    Object.entries(callers).forEach(([symbol, callerList], idx) => {
      // We don't perfectly know which file the symbol is in vs the caller, 
      // but we link all changed files to all affected files to represent the blast radius visually
      changedFiles.forEach((changed) => {
        affectedFiles.forEach((affected) => {
           const edgeId = `e-${changed}-${affected}-${idx}`;
           if (!initialEdges.find(e => e.source === changed && e.target === affected)) {
             initialEdges.push({
                id: edgeId,
                source: changed,
                target: affected,
                animated: true,
                style: { stroke: 'rgba(139, 92, 246, 0.5)', strokeWidth: 2 },
                markerEnd: {
                  type: MarkerType.ArrowClosed,
                  color: 'rgba(139, 92, 246, 0.8)',
                },
             });
           }
        });
      });
    });

    return { nodes: initialNodes, edges: initialEdges };
  }, [changedFiles, affectedFiles, callers]);

  return (
    <div className="h-[400px] w-full rounded-2xl border border-white/[0.07] bg-black/40 overflow-hidden relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        className="bg-transparent"
        proOptions={{ hideAttribution: true }}
      >
        <Background color="rgba(255,255,255,0.05)" gap={16} />
        <Controls className="fill-white bg-white/10 border-white/20" />
        <Panel position="top-left" className="bg-black/50 backdrop-blur-md p-3 rounded-xl border border-white/10 m-4">
          <div className="flex items-center gap-2 mb-2">
            <Network className="h-4 w-4 text-violet-400" />
            <span className="text-xs font-bold text-white uppercase tracking-wider">Dependency Graph</span>
          </div>
          <div className="flex flex-col gap-1 text-[11px] text-white/50">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-rose-500"></span> Modified Source
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-orange-500"></span> Blast Radius Impact
            </div>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
}
