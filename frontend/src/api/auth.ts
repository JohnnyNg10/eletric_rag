import type { LoginRequest, TokenResponse, UserInfo, RefreshResponse } from '../types/auth';
import { requestJson, requestResponse } from './client';

export async function login(data: LoginRequest) {
  return requestJson<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getCurrentUser(token: string) {
  return requestJson<UserInfo>('/auth/me', {
    method: 'GET',
  }, { token, timeoutMs: 100000 });
}

export async function refreshAccessToken(refreshToken: string) {
  return requestJson<RefreshResponse>('/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function logout(token: string) {
  return requestResponse('/auth/logout', {
    method: 'POST',
  }, { token, timeoutMs: 50000 });
}
