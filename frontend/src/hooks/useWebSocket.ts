import { useEffect, useRef, useState, useCallback } from 'react';

type MessageHandler = (msg: Record<string, unknown>) => void;

export function useWebSocket(tableId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef<MessageHandler | null>(null);

  const onMessage = useCallback((handler: MessageHandler) => {
    handlerRef.current = handler;
  }, []);

  useEffect(() => {
    if (!tableId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const url = `${protocol}://${host}/ws/${tableId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handlerRef.current?.(msg);
      } catch { /* ignore malformed */ }
    };

    return () => { ws.close(); };
  }, [tableId]);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { connected, send, onMessage };
}
