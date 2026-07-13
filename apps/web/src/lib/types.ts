// Shared API response shapes for Milestone 1 auth/settings screens.

export type User = {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  mfa_enabled: boolean;
  created_at: string;
};

export type Workspace = {
  id: string;
  name: string;
  type: string;
  plan_tier: string;
  owner_id: string;
  created_at: string;
};

export type Tokens = {
  access: string;
  refresh: string;
};

export type AuthSuccess = {
  user: User;
  workspace: Workspace;
  tokens: Tokens;
};

export type LoginResponse =
  | { tokens: Tokens; mfa_required?: undefined }
  | { mfa_required: true; mfa_token: string };

export type ProviderCredential = {
  id: string;
  label: string;
  deployment_mode: "deepseek_cloud";
  masked_key: string;
  is_default: boolean;
  created_at: string;
};
