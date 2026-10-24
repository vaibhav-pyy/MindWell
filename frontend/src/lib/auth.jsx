import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, setUnauthenticatedHandler } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.get('/api/auth/me');
      setUser(data.user);
      return data.user;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setUnauthenticatedHandler(() => setUser(null));
    refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({
      user,
      loading,
      refresh,
      setUser,
      async login(email, password, role) {
        const data = await api.post('/api/auth/login', { email, password, role });
        setUser(data.user);
        return data.user;
      },
      async register(form) {
        const data = await api.post('/api/auth/register', form);
        setUser(data.user);
        return data.user;
      },
      async logout() {
        try {
          await api.post('/api/auth/logout');
        } finally {
          setUser(null);
        }
      },
    }),
    [user, loading, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
