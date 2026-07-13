import type { UserInfo } from '../types/auth';
import { DEFAULT_API_BASE_URL } from './constants';

const STORAGE_KEYS = {
  apiBaseUrl: 'electric-rag.api-base-url',
  auth: 'electric-rag.auth',
} as const;

export interface StoredAuth {
  accessToken: string;
  refreshToken: string;
  user: UserInfo | null;
}

function canUseStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function getStoredApiBaseUrl() {
  if (!canUseStorage()) return DEFAULT_API_BASE_URL;
  return window.localStorage.getItem(STORAGE_KEYS.apiBaseUrl)?.trim() || DEFAULT_API_BASE_URL;
}

export function setStoredApiBaseUrl(value: string) {
  if (!canUseStorage()) return;
  const nextValue = value.trim() || DEFAULT_API_BASE_URL;
  window.localStorage.setItem(STORAGE_KEYS.apiBaseUrl, nextValue);
}

export function getStoredAuth(): StoredAuth | null {
  if (!canUseStorage()) return null;
  const rawValue = window.localStorage.getItem(STORAGE_KEYS.auth);
  if (!rawValue) return null;

  try {
    const parsed = JSON.parse(rawValue) as StoredAuth;
    if (!parsed.accessToken) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function setStoredAuth(value: StoredAuth | null) {
  if (!canUseStorage()) return;
  if (!value || !value.accessToken) {
    window.localStorage.removeItem(STORAGE_KEYS.auth);
    return;
  }
  window.localStorage.setItem(STORAGE_KEYS.auth, JSON.stringify(value));
}

export function clearStoredAuth() {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(STORAGE_KEYS.auth);
}
