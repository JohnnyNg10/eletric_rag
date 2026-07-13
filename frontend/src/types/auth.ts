export type UserRole = 'admin' | 'user' | 'readonly';

export interface UserInfo {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  full_name?: string | null;
  query_count?: number;
  last_login_at?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserInfo;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}
