import { SyncMonitor } from "@/components/dashboard/sync-monitor"

export default function Home() {
  return (
    <main className="container mx-auto py-10 px-4 md:px-6">
      <h1 className="text-4xl font-extrabold tracking-tight lg:text-5xl mb-10 text-slate-800 border-b pb-4 border-slate-200">
        FlowNote Dashboard
      </h1>
      <SyncMonitor />
    </main>
  )
}
