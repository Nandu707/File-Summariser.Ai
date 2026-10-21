import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Configure axios globally to always include credentials for cookies
axios.defaults.withCredentials = true;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => {
    try {
      return localStorage.getItem('auth_token') || null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  // Synchronize axios authorization header
  const updateAuthHeader = useCallback((authToken) => {
    if (authToken) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${authToken}`;
    } else {
      delete axios.defaults.headers.common['Authorization'];
    }
  }, []);

  // Check current session on mount
  useEffect(() => {
    let isMounted = true;
    const verifySession = async () => {
      const storedToken = localStorage.getItem('auth_token');
      if (storedToken) {
        updateAuthHeader(storedToken);
      }

      try {
        const res = await axios.get(`${API_BASE_URL}/api/auth/me`);
        if (isMounted && res.data) {
          setUser(res.data);
          if (storedToken) setToken(storedToken);
        }
      } catch (err) {
        if (isMounted) {
          setUser(null);
          setToken(null);
          try {
            localStorage.removeItem('auth_token');
          } catch {}
          updateAuthHeader(null);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    verifySession();
    return () => { isMounted = false; };
  }, [updateAuthHeader]);

  // Intercept 401 responses to automatically redirect to login
  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response && error.response.status === 401) {
          const reqUrl = error.config?.url || '';
          // Do not reset user if 401 came from login or signup attempts
          if (!reqUrl.includes('/api/auth/login') && !reqUrl.includes('/api/auth/signup')) {
            setUser(null);
            setToken(null);
            try {
              localStorage.removeItem('auth_token');
            } catch {}
            updateAuthHeader(null);
          }
        }
        return Promise.reject(error);
      }
    );
    return () => axios.interceptors.response.eject(interceptor);
  }, [updateAuthHeader]);

  const login = async (email, password) => {
    const res = await axios.post(`${API_BASE_URL}/api/auth/login`, {
      email,
      password,
    });
    const { token: newToken, user: userData } = res.data;
    setToken(newToken);
    setUser(userData);
    try {
      localStorage.setItem('auth_token', newToken);
    } catch {}
    updateAuthHeader(newToken);
    return userData;
  };

  const signup = async (name, email, password) => {
    const res = await axios.post(`${API_BASE_URL}/api/auth/signup`, {
      name,
      email,
      password,
    });
    const { token: newToken, user: userData } = res.data;
    setToken(newToken);
    setUser(userData);
    try {
      localStorage.setItem('auth_token', newToken);
    } catch {}
    updateAuthHeader(newToken);
    return userData;
  };

  const logout = async () => {
    try {
      await axios.post(`${API_BASE_URL}/api/auth/logout`);
    } catch (e) {
      console.warn("Logout error:", e);
    } finally {
      setUser(null);
      setToken(null);
      try {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('task_rag_active_doc_id');
        localStorage.removeItem('task_rag_active_chat_id');
        sessionStorage.clear();
      } catch {}
      updateAuthHeader(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        isAuthenticated: !!user,
        login,
        signup,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
