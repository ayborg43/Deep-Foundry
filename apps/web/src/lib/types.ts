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
  deployment_mode: "deepseek_cloud" | "deepseek_self_hosted";
  endpoint_url?: string | null;
  masked_key: string;
  is_default: boolean;
  created_at: string;
};

// --- Milestone 3: Coworkers & tools ------------------------------------

export type RiskClassification = "safe" | "sensitive" | "dangerous";

export type Tool = {
  id: string;
  name: string;
  description: string;
  risk_classification: RiskClassification;
  input_schema: unknown;
  output_schema: unknown;
  provider: string;
  created_at: string;
};

export type ModelId =
  | "deepseek-v4-flash"
  | "deepseek-v4-pro";

export type ModelBinding = {
  primary: ModelId;
  fallback?: ModelId[];
};

export type PermissionProfile = {
  safe: "auto" | "approval";
  sensitive: "auto" | "approval";
  dangerous: "auto" | "approval";
};

// The Coworker.attached_tools[].id field is documented only as "id" in the
// contract, with no separate attachment-id concept anywhere else in the
// API (DELETE takes tool_id, POST attach is keyed by tool_id). We treat it
// as the tool's id — see AGENTS.md-equivalent note in coworkers/[id]/page.tsx.
export type AttachedTool = {
  id: string;
  name: string;
  enabled: boolean;
};

export type Coworker = {
  id: string;
  name: string;
  avatar_url: string | null;
  owner_type: "user" | "team" | "organization";
  owner_id: string;
  role_description: string;
  model_binding: ModelBinding;
  permission_profile: PermissionProfile;
  attached_tools: AttachedTool[];
  status: "active" | "archived";
  current_version: number;
  created_at: string;
};

// --- Phase 2: organizations, teams, workflows and marketplace --------

export type AgentTeamMember = {
  id: string;
  coworker_id: string;
  coworker_name: string;
  role: "manager" | "researcher" | "writer" | "reviewer" | "developer" | "tester" | "security_reviewer" | "architect" | "planner" | "product_manager" | "custom";
  custom_role_label: string;
  position: number;
};

export type AgentTeam = {
  id: string;
  workspace_id: string;
  name: string;
  collaboration_pattern: "manager_delegate" | "sequential" | "parallel_merge";
  version: number;
  members: AgentTeamMember[];
};

export type WorkflowStep = {
  id?: string;
  type?: "coworker_action" | "tool_call" | "human_checkpoint" | "condition";
  step_type?: "coworker_action" | "tool_call" | "human_checkpoint" | "condition";
  title?: string;
  status?: "pending" | "in_progress" | "needs_approval" | "completed" | "failed";
  coworker_id?: string;
  tool_name?: string;
  instructions?: string;
  definition?: Record<string, unknown>;
  result?: Record<string, unknown>;
};

export type Workflow = {
  id: string;
  workspace_id: string;
  name: string;
  version: number;
  definition: { steps: WorkflowStep[] };
  triggers: Array<{ id: string; trigger_type: "manual" | "scheduled" | "event"; schedule_cron: string | null; event_source: string | null; enabled: boolean; next_run_at: string | null }>;
};

export type WorkflowRun = {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version: number;
  triggered_by: string;
  status: "pending" | "running" | "needs_approval" | "completed" | "failed";
  current_step_index: number;
  steps: WorkflowStep[];
  started_at: string;
  completed_at: string | null;
};

export type MarketplaceListing = {
  id: string;
  name: string;
  summary: string;
  listing_type: "skill" | "capability_pack" | "workflow_template";
  pricing_model: "free" | "paid" | "pay_what_you_want";
  price_usd: string | null;
  verified_publisher: boolean;
  latest_version: string | null;
  install_count: number;
  review_count: number;
  rating: number | null;
  manifest?: Record<string, unknown>;
  security_review?: { score: number; status: "passed" | "needs_review" | "failed"; findings: Array<{ severity: string; code: string; message: string }> };
};

export type Integration = {
  id: string;
  kind: "email" | "calendar" | "slack" | "discord" | "github" | "webhook";
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  workspace_token: string;
};

// --- Phase 3: enterprise governance and marketplace economy ----------

export type EnterpriseSettings = {
  data_region: "us" | "eu" | "uk" | "ca" | "au" | "self_hosted";
  retention_days: number;
  legal_hold: boolean;
  support_tier: "community" | "standard" | "premium" | "dedicated";
  sla_uptime_percent: string;
  sla_response_minutes: number;
};

export type SSOProvider = {
  id: string; name: string; protocol: "saml" | "oidc"; issuer: string;
  sso_url: string; entity_id: string; client_id: string; email_domains: string[];
  jit_provisioning: boolean; enforce_sso: boolean; enabled: boolean;
};

export type PolicyRule = {
  id: string; name: string; resource_type: string; action: string;
  conditions: Record<string, unknown>; effect: "allow" | "deny" | "require_approval";
  priority: number; enabled: boolean;
};

export type AuditAnomaly = {
  id: string; anomaly_type: string; severity: "low" | "medium" | "high" | "critical";
  summary: string; evidence: Record<string, unknown>; status: "open" | "acknowledged" | "resolved";
  detected_at: string;
};

export type Artifact = {
  id: string; artifact_type: "presentation" | "diagram" | "video_analysis" | "coworker_bundle" | "compliance";
  name: string; content: Record<string, unknown>; checksum: string; created_at: string;
};

// --- Phase 4: adaptive collaboration ---------------------------------

export type CapabilityProposal = {
  id: string; coworker_id: string; coworker_name: string;
  proposed_by_type: "coworker" | "user"; target_type: "tool" | "skill";
  target_id: string; target_name: string; rationale: string;
  status: "pending" | "approved" | "denied"; created_at: string;
};

export type MemoryConflict = {
  id: string; subject: string; left_memory_id: string; right_memory_id: string;
  left_content: string; right_content: string; status: "open" | "resolved";
  resolution_strategy: "" | "keep_left" | "keep_right" | "merge";
  resolved_content: string; created_at: string;
};

export type ConsensusSession = {
  id: string; agent_team_id: string; agent_team_name: string; question: string;
  options: string[]; method: "majority" | "unanimous" | "confidence_weighted";
  status: "collecting" | "decided" | "deadlocked"; result_option: string;
  created_at: string; completed_at: string | null;
  votes: Array<{ id: string; coworker_id: string; coworker_name: string; option: string; confidence: string; rationale: string }>;
};

export type VoiceSession = {
  id: string; workspace_id: string; coworker_id: string; coworker_name: string;
  conversation_id: string; language: string; status: "active" | "ended";
  started_at: string; ended_at: string | null;
};

export type CoworkerVersion = {
  id: string;
  version_number: number;
  role_description: string;
  model_binding: ModelBinding;
  permission_profile: PermissionProfile;
  created_by_id: string;
  created_at: string;
  changelog: string | null;
};

export type CoworkerToolAttachment = {
  id: string;
  tool: Tool;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
};

// --- Milestone 4: Chat --------------------------------------------------

export type Conversation = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  created_by: string | null;
  title: string;
  coworker_id: string | null;
  created_at: string;
};

export type MessageSenderType = "user" | "coworker" | "system";
export type MessageStatus =
  | "pending"
  | "streaming"
  | "needs_approval"
  | "complete"
  | "failed";

export type ToolCallRequest = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  sender_type: MessageSenderType;
  sender_id: string | null;
  content: string;
  tool_calls: ToolCallRequest[] | null;
  tool_call_id: string | null;
  parent_message_id: string | null;
  status: MessageStatus;
  created_at: string;
};

export type ApprovalRequestStatus = "pending" | "approved" | "denied" | "expired";

export type ApprovalRequestData = {
  id: string;
  coworker_id: string;
  tool_id: string;
  tool_name: string;
  tool_risk_classification?: RiskClassification;
  coworker_name?: string;
  task_title?: string | null;
  conversation_id: string | null;
  message_id: string | null;
  task_id: string | null;
  workflow_run_step_id: string | null;
  requested_action: { tool_call_id?: string; name?: string; arguments?: Record<string, unknown> };
  status: ApprovalRequestStatus;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
};

// --- Milestone 5: Memory & knowledge ---------------------------------

export type MemoryEntry = {
  id: string;
  workspace_id: string;
  scope: "user" | "coworker" | "project" | "organization" | "temporary";
  scope_id: string;
  content: string;
  source_type: "conversation" | "task_result" | "manual" | "workflow_run";
  source_ref_id: string | null;
  is_long_term: boolean;
  promoted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeDocument = {
  id: string;
  knowledge_base_id: string;
  source_uri: string;
  mime_type: string;
  ingestion_status: "pending" | "chunking" | "embedding" | "ready" | "failed";
  ingestion_error: string;
  last_crawled_at: string | null;
  created_at: string;
};

export type KnowledgeBase = {
  id: string;
  workspace_id: string;
  scope: "coworker" | "project" | "workspace";
  scope_id: string;
  name: string;
  source_type: string;
  attached_coworker_ids: string[];
  documents?: KnowledgeDocument[];
  created_at: string;
};

// --- Milestone 6: Tasks & notifications -------------------------------

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "needs_approval"
  | "blocked"
  | "completed"
  | "failed";

export type BackgroundTask = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  coworker_id: string;
  coworker_name: string;
  created_by_type: "user" | "coworker" | "workflow";
  created_by_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  due_at: string | null;
  parent_task_id: string | null;
  result: string;
  error_message: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type Notification = {
  id: string;
  workspace_id: string;
  type: "task_completed" | "approval_requested" | "workflow_failed" | "mention" | "billing";
  payload: {
    task_id?: string;
    approval_request_id?: string;
    title?: string;
    status?: TaskStatus;
    tool_name?: string;
  };
  read_at: string | null;
  created_at: string;
};

// --- Milestone 7: Observability ---------------------------------------

export type AuditLogEntry = {
  id: string;
  actor_type: "user" | "coworker" | "system";
  actor_id: string | null;
  actor_label: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AuditLogPage = {
  count: number;
  next_offset: number | null;
  results: AuditLogEntry[];
};

export type UsageBreakdown = {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
};

export type UsageReport = {
  range: string;
  from: string;
  to: string;
  totals: UsageBreakdown & { average_latency_ms: number };
  by_coworker: Array<UsageBreakdown & { coworker_id: string | null; coworker_name: string }>;
  by_provider: Array<UsageBreakdown & { deployment_mode: string; model_id: string }>;
  daily: Array<{ date: string; calls: number; cost_usd: string }>;
};
