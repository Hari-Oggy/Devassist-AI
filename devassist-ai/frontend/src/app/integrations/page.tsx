import { Sidebar } from "@/components/Sidebar";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Info, Plus } from "lucide-react";

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
    <div className="flex h-screen overflow-hidden bg-[#16151a]">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl p-8">
          <div className="flex items-center justify-between mb-8 pb-4 border-b border-zinc-800">
            <h1 className="text-xl font-medium text-white">Integrations</h1>
            <Button variant="outline" className="bg-transparent border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white h-8 text-xs">
              <Plus className="mr-1.5 h-3 w-3" />
              New MCP Server
            </Button>
          </div>

          <Tabs defaultValue="mcp" className="w-full max-w-3xl">
            <TabsList className="bg-zinc-900/50 border border-zinc-800 p-1 mb-6 rounded-md">
              <TabsTrigger value="mcp" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400">MCP Servers</TabsTrigger>
              <TabsTrigger value="issue" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400">Issue Tracking</TabsTrigger>
              <TabsTrigger value="cicd" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400">CI/CD</TabsTrigger>
            </TabsList>
            
            <TabsContent value="mcp" className="space-y-4">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 flex gap-3 items-start mb-6">
                <Info className="h-5 w-5 text-zinc-500 shrink-0 mt-0.5" />
                <p className="text-sm text-zinc-400">
                  MCP server connections are shared across your organization. To maintain least privilege, we recommend configuring with a <span className="font-semibold text-zinc-300">service account</span> or <span className="font-semibold text-zinc-300">scoped credentials</span>.
                </p>
              </div>

              <div className="space-y-3">
                {integrations.map((integration) => (
                  <div key={integration.name} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 hover:bg-zinc-800/40 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-md bg-zinc-800 text-zinc-300 font-bold">
                        {integration.icon}
                      </div>
                      <div>
                        <h3 className="text-base font-medium text-zinc-200">{integration.name}</h3>
                        <p className="text-xs text-zinc-500">{integration.domain}</p>
                      </div>
                    </div>
                    <Button variant="outline" size="sm" className="bg-transparent border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white h-8">
                      <Plus className="mr-1.5 h-3 w-3" />
                      Add
                    </Button>
                  </div>
                ))}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
