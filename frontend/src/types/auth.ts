export interface AuthUser {
  id: number;
  username: string;
  role: string;
  email?: string;
  is_active?: boolean;
  must_change_password?: boolean;
  created_at?: string;
  last_login?: string;
}

export interface LoginResponse {
  token: string;
  user: { id: number; username: string; role: string };
}

export interface SSOConfig {
  enabled: boolean;
  client_id?: string;
  authorize_url?: string;
  redirect_uri?: string;
  audience?: string;
}
