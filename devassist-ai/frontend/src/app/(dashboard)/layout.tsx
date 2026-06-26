import { Sidebar } from "@/components/Sidebar";
import { ConnectionErrorBanner } from "@/components/ConnectionErrorBanner";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "oklch(0.08 0.01 265)" }}>
      <Sidebar />
      <main className="flex-1 overflow-y-auto animated-gradient-bg flex flex-col">
        <ConnectionErrorBanner />
        <div className="flex-1">
          {children}
        </div>
      </main>
    </div>
  );
}
