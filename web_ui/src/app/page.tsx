// web_ui/src/app/page.tsx

import { SyncMonitor } from "@/components/dashboard/sync-monitor"
import StatsView from "@/components/dashboard/stats/StatsView"

export default function Home() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Dashboard</h1>
        <p className="text-slate-500">Manage your PARA knowledge system and automations.</p>
      </div>
      
      {/* 1. Sync Monitor Section */}
      <div className="grid grid-cols-1">
         <SyncMonitor />
      </div>

      {/* 2. Stats Section */}
      <div>
         <h2 className="text-xl font-semibold text-slate-800 mb-4">Analytics Overview</h2>
         <StatsView />
      </div>
    </div>
  )
}

