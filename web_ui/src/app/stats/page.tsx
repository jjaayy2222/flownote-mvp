// web_ui/src/app/stats/page.tsx

import StatsView from "@/components/dashboard/stats/StatsView";

export default function StatsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Statistics</h2>
      </div>
      <StatsView />
    </div>
  );
}
