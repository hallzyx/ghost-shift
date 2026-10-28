import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';

export interface Polled<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (d: T) => void;
}

/**
 * Carga un recurso y lo vuelve a pedir cada `interval` ms mientras `keepPolling(data)` sea true.
 * Un error de red detiene el polling y se expone para mostrar «Reintentar».
 */
export function usePolling<T>(
  key: string | undefined,
  fetcher: () => Promise<T>,
  keepPolling: (d: T) => boolean,
  interval = 1500,
): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const fetchRef = useRef(fetcher);
  const keepRef = useRef(keepPolling);
  fetchRef.current = fetcher;
  keepRef.current = keepPolling;

  useEffect(() => {
    if (!key) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const d = await fetchRef.current();
        if (!alive) return;
        setData(d);
        setError(null);
        setLoading(false);
        if (keepRef.current(d)) timer = window.setTimeout(tick, interval);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof ApiError ? e : new ApiError(0, String(e), true));
        setLoading(false);
      }
    };
    setLoading(true);
    void tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [key, interval, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}
