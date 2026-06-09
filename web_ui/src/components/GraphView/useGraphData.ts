import { useCallback, useEffect, useState, useRef } from "react";
import { toast } from "sonner";
import { API_BASE } from "@/lib/api";
import type { GraphViewData } from "./types";

export function useGraphData() {
  const [data, setData] = useState<GraphViewData | null>(null);
  const [loading, setLoading] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async () => {
    // 이전 요청이 있다면 취소
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    // 새로운 컨트롤러 생성
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/graph/data`, { signal: controller.signal });
      if (!res.ok) throw new Error("Failed to fetch graph data");
      const fetchedData: GraphViewData = await res.json();
      setData(fetchedData);
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return; // Ignore abort errors
      console.error("Error fetching graph data:", error);
      toast.error("Failed to load graph data");
    } finally {
      // 현재 실행 중인 요청과 완료된 요청이 일치할 때만 로딩 상태 해제
      if (abortControllerRef.current === controller) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchData();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchData]);

  return { data, loading, reload: fetchData };
}
