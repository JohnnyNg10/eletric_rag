import { useCallback, useEffect, useState } from 'react';
import { getCurrentUser, login, logout, refreshAccessToken } from '../api/auth';
import { getErrorMessage } from '../api/client';
import type { UserInfo } from '../types/auth';
import {
  clearStoredAuth,
  getStoredApiBaseUrl,
  getStoredAuth,
  setStoredApiBaseUrl,
  setStoredAuth,
} from '../utils/storage';

const initialStoredAuth = getStoredAuth();

// 定时刷新间隔：25分钟（token 过期时间 30 分钟，提前 5 分钟刷新）
const TOKEN_REFRESH_INTERVAL = 25 * 60 * 1000;

export function useAuth() {
  const [apiBaseUrl, setApiBaseUrlState] = useState(getStoredApiBaseUrl());
  const [accessToken, setAccessToken] = useState(initialStoredAuth?.accessToken ?? '');
  const [refreshToken, setRefreshToken] = useState(initialStoredAuth?.refreshToken ?? '');
  const [user, setUser] = useState<UserInfo | null>(initialStoredAuth?.user ?? null);
  const [isLoading, setIsLoading] = useState(Boolean(initialStoredAuth?.accessToken));
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const persistAuth = useCallback((nextAccessToken: string, nextRefreshToken: string, nextUser: UserInfo | null) => {
    if (!nextAccessToken) {
      clearStoredAuth();
      return;
    }

    setStoredAuth({
      accessToken: nextAccessToken,
      refreshToken: nextRefreshToken,
      user: nextUser,
    });
  }, []);

  const handleLogout = useCallback(async () => {
    if (accessToken) {
      try {
        await logout(accessToken);
      } catch {
        // 忽略服务端登出失败，直接清理本地状态
      }
    }

    clearStoredAuth();
    setAccessToken('');
    setRefreshToken('');
    setUser(null);
    setError(null);
    setIsLoading(false);
  }, [accessToken]);

  const handleLogin = useCallback(
    async (username: string, password: string) => {
      setIsLoggingIn(true);
      setError(null);

      try {
        const response = await login({ username, password });
        setAccessToken(response.access_token);
        setRefreshToken(response.refresh_token);
        setUser(response.user);
        persistAuth(response.access_token, response.refresh_token, response.user);
      } catch (loginError) {
        setError(getErrorMessage(loginError, '登录失败，请检查用户名和密码'));
        throw loginError;
      } finally {
        setIsLoggingIn(false);
      }
    },
    [persistAuth],
  );

  const updateApiBaseUrl = useCallback((value: string) => {
    const nextValue = value.trim() || getStoredApiBaseUrl();
    setApiBaseUrlState(nextValue);
    setStoredApiBaseUrl(nextValue);
  }, []);


  const updateManualToken = useCallback(
    (value: string) => {
      const nextToken = value.trim();
      setAccessToken(nextToken);
      setRefreshToken('');
      setUser(null);
      setError(null);
      setIsLoading(Boolean(nextToken));
      persistAuth(nextToken, '', null);
    },
    [persistAuth],
  );

  useEffect(() => {
    if (!accessToken || user) {
      setIsLoading(false);
      return;
    }

    let active = true;
    setIsLoading(true);

    getCurrentUser(accessToken)
      .then((profile) => {
        if (!active) return;
        setUser(profile);
        setError(null);
        persistAuth(accessToken, refreshToken, profile);
      })
      .catch((profileError) => {
        if (!active) return;
        setError(getErrorMessage(profileError, '登录状态已失效，请重新登录'));
        clearStoredAuth();
        setAccessToken('');
        setRefreshToken('');
        setUser(null);
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [accessToken, persistAuth, refreshToken, user]);

  // 定时刷新 token（已登录且有 refreshToken 时启动）
  useEffect(() => {
    if (!accessToken || !refreshToken || !user) {
      return;
    }

    const timerId = setInterval(async () => {
      try {
        const response = await refreshAccessToken(refreshToken);
        const newAccessToken = response.access_token;

        setAccessToken(newAccessToken);
        persistAuth(newAccessToken, refreshToken, user);

        console.log('[useAuth] Token auto-refreshed');
      } catch (refreshError) {
        console.error('[useAuth] Auto-refresh failed:', refreshError);
        // 刷新失败不强制登出，让 401 拦截器处理
      }
    }, TOKEN_REFRESH_INTERVAL);

    return () => {
      clearInterval(timerId);
    };
  }, [accessToken, refreshToken, user, persistAuth]);

  return {
    apiBaseUrl,
    accessToken,
    refreshToken,
    user,
    isLoading,
    isLoggingIn,
    error,
    login: handleLogin,
    logout: handleLogout,
    updateApiBaseUrl,
    updateManualToken,
  };
}
