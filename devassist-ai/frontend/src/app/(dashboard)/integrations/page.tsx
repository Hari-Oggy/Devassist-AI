"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Info, Plus, Cable } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader, GlassCard } from "@/components/ui/shared";

const integrations = [
  { name: 'Notion', domain: 'mcp.notion.com', icon: 'N' },
  { name: 'Context7', domain: 'mcp.context7.com', icon: 'C' },
  { name: 'Linear', domain: 'mcp.linear.app', icon: 'L' },
  { name: 'GitHub Copilot', domain: 'api.githubcopilot.com', icon: 'G' },
  { name: 'Sentry', domain: 'mcp.sentry.dev', icon: 'S' },
  { name: 'Asana', domain: 'mcp.asana.com', icon: 'A' },
  { name: 'Monday.com', domain: 'mcp.monday.com', icon: 'M' },
];

export default function Integrations() {
  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <PageHeader
        title="Integrations"
        subtitle="Manage MCP Server connections and developer tools integrations."
        action={
          <Button variant="outline" className="bg-white/[0.03] hover:bg-white/[0.06] text-white/70 border-white/10 shadow-sm h-10 px-4 rounded-xl text-[13px] font-medium gap-2">
            <Plus className="h-4 w-4" />
            New MCP Server
          </Button>
        }
      />

      <Tabs defaultValue="mcp" className="w-full">
        <TabsList className="bg-white/[0.03] border border-white/[0.07] p-1 mb-6 rounded-xl">
          <TabsTrigger value="mcp" className="data-[state=active]:bg-white/[0.06] data-[state=active]:text-white text-white/40 rounded-lg text-[13px] font-semibold px-4 py-2">
            MCP Servers
          </TabsTrigger>
          <TabsTrigger value="issue" className="data-[state=active]:bg-white/[0.06] data-[state=active]:text-white text-white/40 rounded-lg text-[13px] font-semibold px-4 py-2">
            Issue Tracking
          </TabsTrigger>
          <TabsTrigger value="cicd" className="data-[state=active]:bg-white/[0.06] data-[state=active]:text-white text-white/40 rounded-lg text-[13px] font-semibold px-4 py-2">
            CI/CD
          </TabsTrigger>
        </TabsList>
        
        <TabsContent value="mcp" className="space-y-6">
          <GlassCard className="flex gap-4 items-start">
            <Info className="h-5 w-5 text-violet-400 shrink-0 mt-0.5" />
            <p className="text-[13px] text-white/50 leading-relaxed">
              MCP server connections are shared across your organization. To maintain least privilege, we recommend configuring with a <span className="font-semibold text-white/75">service account</span> or <span className="font-semibold text-white/75">scoped credentials</span>.
            </p>
          </GlassCard>

          <div className="grid gap-4">
            {integrations.map((integration) => (
              <GlassCard key={integration.name} noPad className="hover:border-white/[0.12] hover:bg-white/[0.04] transition-all duration-300">
                <div className="p-5 flex items-center justify-between gap-6">
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.04] border border-white/[0.07] text-white font-bold">
                      {integration.icon}
                    </div>
                    <div>
                      <h3 className="text-[14px] font-bold text-white">{integration.name}</h3>
                      <p className="text-[12px] text-white/40 mt-0.5">{integration.domain}</p>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="bg-violet-500/5 border-violet-500/20 text-violet-400 hover:bg-violet-500/10 hover:border-violet-500/30 font-bold text-[12px] h-9 px-4 rounded-xl transition-all duration-200">
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    Configure
                  </Button>
                </div>
              </GlassCard>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
