import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

import { addAuthChangeListener, logout, rehydrateAuth } from './api';

export type Theme = 'light' | 'dark';

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

export interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

export interface AuthContextValue {
  authenticated: boolean;
  handleLogin: () => void;
  handleLogout: () => void;
}

export const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: 'light',
  toggle: () => {},
});

export const ToastContext = createContext<ToastContextValue>({
  toast: () => {},
});

export const AuthContext = createContext<AuthContextValue>({
  authenticated: false,
  handleLogin: () => {},
  handleLogout: () => {},
});

export const useTheme = () => useContext(ThemeContext);

export const useToast = () => useContext(ToastContext);

export const useAuth = () => useContext(AuthContext);

let nextToastId = 0;

export const useToastController = () => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer) clearTimeout(timer);
    timersRef.current.delete(id);
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message: string, type: ToastType = 'success') => {
    const id = ++nextToastId;
    setToasts((prev) => [...prev.slice(-4), { id, message, type }]);
    const timer = setTimeout(() => removeToast(id), type === 'error' ? 6000 : 3500);
    timersRef.current.set(id, timer);
  }, [removeToast]);

  return { toasts, addToast, removeToast };
};

export const useAuthController = () => {
  const [authenticated, setAuthenticated] = useState(false);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    let active = true;

    void rehydrateAuth()
      .then((value) => {
        if (!active) return;
        setAuthenticated(value);
        setAuthReady(true);
      })
      .catch((error) => {
        console.error('Auth rehydration failed', error);
        if (!active) return;
        setAuthenticated(false);
        setAuthReady(true);
      });

    const unsubscribe = addAuthChangeListener((value) => {
      if (!active) return;
      setAuthenticated(value);
      setAuthReady(true);
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const handleLogin = useCallback(() => setAuthenticated(true), []);
  const handleLogout = useCallback(() => {
    logout();
    setAuthenticated(false);
  }, []);

  return { authenticated, authReady, handleLogin, handleLogout };
};
