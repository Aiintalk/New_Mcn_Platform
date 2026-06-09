export interface UserInfo {
  id: number;
  username: string;
  real_name: string;
  role: 'admin' | 'operator';
  status: 'enabled' | 'disabled';
  must_change_password: boolean;
  last_login_at: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  must_change_password: boolean;
  user: UserInfo;
}
