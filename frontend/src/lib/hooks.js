import { useCallback, useEffect, useState } from 'react';
import { api } from './api';

// Load data from a GET endpoint with loading/error state and a reload function.
export function useApi(url, { enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(enabled);

  const reload = useCallback(async () => {
    if (!url) return null;
    setLoading(true);
    setError(null);
    try {
      const result = await api.get(url);
      setData(result);
      return result;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    if (enabled) reload();
  }, [reload, enabled]);

  return { data, setData, error, loading, reload };
}

export function formatDate(iso, opts = { day: 'numeric', month: 'short' }) {
  if (!iso) return '';
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return d.toLocaleDateString(undefined, opts);
}

export function formatDateTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
}
