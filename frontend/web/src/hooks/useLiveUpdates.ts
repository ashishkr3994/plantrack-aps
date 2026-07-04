// Live updates over WebSocket. Connects to the backend hub, surfaces connection
// state, and invalidates the relevant React Query caches when the server pushes
// an event (e.g. a solve finished, an alert was raised) so connected planners
// see changes without manual refresh. Auto-reconnects with backoff.
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { qk } from "./queries";

export type LiveStatus = "connecting" | "live" | "offline";

interface ServerEvent {
  type: "schedule_updated" | "alert_raised" | "order_changed" | "ping";
  payload?: Record<string, unknown>;
}

function wsUrl(): string {
  const base = import.meta.env.VITE_WS_URL as string | undefined;
  if (base) return base;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

export function useLiveUpdates() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const [lastEvent, setLastEvent] = useState<ServerEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retry = useRef(0);
  const closed = useRef(false);

  useEffect(() => {
    closed.current = false;

    const connect = () => {
      setStatus(retry.current === 0 ? "connecting" : "connecting");
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        retry.current = 0;
        setStatus("live");
      };
      ws.onmessage = (ev) => {
        let msg: ServerEvent;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.type === "ping") return;
        setLastEvent(msg);
        // refresh affected views
        if (msg.type === "schedule_updated") {
          qc.invalidateQueries({ queryKey: qk.watchlist });
          qc.invalidateQueries({ queryKey: qk.summary });
        } else if (msg.type === "alert_raised") {
          qc.invalidateQueries({ queryKey: qk.summary });
        } else if (msg.type === "order_changed") {
          qc.invalidateQueries({ queryKey: qk.orders });
          qc.invalidateQueries({ queryKey: qk.watchlist });
        }
      };
      ws.onclose = () => {
        if (!closed.current) scheduleReconnect();
      };
      ws.onerror = () => {
        ws.close();
      };
    };

    const scheduleReconnect = () => {
      setStatus("offline");
      retry.current += 1;
      const delay = Math.min(1000 * 2 ** retry.current, 15000);
      setTimeout(() => {
        if (!closed.current) connect();
      }, delay);
    };

    connect();
    return () => {
      closed.current = true;
      wsRef.current?.close();
    };
  }, [qc]);

  return { status, lastEvent };
}
