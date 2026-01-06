// web_ui/src/app/graph/page.tsx

import GraphView from "@/components/para/GraphView";

export default function GraphPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">PARA Graph View</h2>
      </div>
      <GraphView />
    </div>
  );
}
