import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getWebSocketUrl } from "@/config/websocket";
import { isWebSocketEvent, WS_EVENT_TYPE } from "@/types/websocket";
import { logger } from "@/lib/logger";
import { UI_CONFIG } from "@/config/ui";
import { getToastThrottleDelay } from "@/lib/ui";

const GRAPH_UPDATE_THROTTLE = getToastThrottleDelay("GRAPH_UPDATE");

export function useGraphLiveUpdates(onGraphUpdated: () => void) {
  const { isConnected, lastMessage } = useWebSocket(getWebSocketUrl(), {
    autoConnect: true,
    reconnect: true,
  });

  const lastToastTimeRef = useRef<number>(0);

  useEffect(() => {
    if (!lastMessage || !isWebSocketEvent(lastMessage)) return;
    if (lastMessage.type !== WS_EVENT_TYPE.GRAPH_UPDATED) return;

    logger.debug("[GraphView] Graph updated event received, reloading data...");
    onGraphUpdated();

    const now = Date.now();
    if (now - lastToastTimeRef.current > GRAPH_UPDATE_THROTTLE) {
      toast.info("Graph data updated", {
        description: "Real-time sync from backend",
        id: UI_CONFIG.TOAST.IDS.GRAPH_UPDATE,
      });
      lastToastTimeRef.current = now;
    }
  }, [lastMessage, onGraphUpdated]);

  return { isConnected };
}
