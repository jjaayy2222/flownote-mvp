import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { API_BASE } from "@/lib/api";
import type { GraphViewData } from "./types";

export function useGraphData() {
  const [data, setData] = useState<GraphViewData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/graph/data`);
      if (!res.ok) throw new Error("Failed to fetch graph data");
      const fetchedData: GraphViewData = await res.json();
      setData(fetchedData);
    } catch (error) {
      console.error("Error fetching graph data:", error);
      toast.error("Failed to load graph data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, reload: fetchData };
}
