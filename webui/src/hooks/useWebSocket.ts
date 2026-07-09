import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`;

export interface WSEvent {
  type: string;
  event?: string;
  data?: Record<string, unknown>;
  timestamp?: string;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<WSEvent[]>([]);
  const handlersRef = useRef<((e: WSEvent) => void)[]>([]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setTimeout(connect, 3000); };
    ws.onerror = () => ws.close();
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as WSEvent;
        setEvents((prev) => [data, ...prev].slice(0, 200));
        handlersRef.current.forEach((h) => h(data));
      } catch { /* ignore */ }
    };
  }, []);

  useEffect(() => { connect(); return () => wsRef.current?.close(); }, [connect]);

  const on = useCallback((handler: (e: WSEvent) => void) => {
    handlersRef.current.push(handler);
    return () => { handlersRef.current = handlersRef.current.filter((h) => h !== handler); };
  }, []);

  return { connected, events, on, send: (data: Record<string, unknown>) => wsRef.current?.send(JSON.stringify(data)) };
}
