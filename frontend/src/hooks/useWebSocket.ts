import { useEffect, useRef, useState, useCallback } from 'react';

type MessageHandler = (msg: Record<string, unknown>) => void;

const INITIAL_RETRY_MS = 1000;
const MAX_BACKOFF_MS = 10_000;

export function useWebSocket(tableId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  // ms until the next reconnect attempt; 0 = no retry pending
  const [reconnectIn, setReconnectIn] = useState(0);
  const handlerRef = useRef<MessageHandler | null>(null);

  const onMessage = useCallback((handler: MessageHandler) => {
    handlerRef.current = handler;
  }, []);

  useEffect(() => {
    if (!tableId) return;

    let disposed = false;
    let retryMs = INITIAL_RETRY_MS;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    // A logged-in client sends its session token so the server can bind the
    // seat to the account (stats → personal profile); guests omit it.
    const token = localStorage.getItem('authToken');
    const url = `${protocol}://${host}/ws/${tableId}${token ? `?token=${encodeURIComponent(token)}` : ''}`;

    const connect = () => {
      setReconnectIn(0);  // attempt in flight — no retry pending
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        retryMs = INITIAL_RETRY_MS; // backoff resets once a connection succeeds
        setConnected(true);
        setReconnectIn(0);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!disposed) {
          setReconnectIn(retryMs);
          timer = setTimeout(connect, retryMs);
          retryMs = Math.min(retryMs * 2, MAX_BACKOFF_MS);
        }
      };
      ws.onerror = () => setConnected(false); // onclose follows and schedules the retry
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handlerRef.current?.(msg);
        } catch { /* ignore malformed */ }
      };
    };

    connect();

    return () => {
      disposed = true;
      if (timer !== null) clearTimeout(timer);
      setReconnectIn(0);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [tableId]);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { connected, reconnectIn, send, onMessage };
}
