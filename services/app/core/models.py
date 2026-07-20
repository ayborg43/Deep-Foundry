"""
Core models — Milestone 0 / Epic 0.2 scope only: users, oauth_identities,
workspaces, workspace_members, per DATABASE.md §2.1.

Every table's primary key is a UUIDv7 per DATABASE.md §1 ("All primary keys
are UUIDv7 (time-ordered, sortable, no central sequence bottleneck)").
Django's AbstractBaseUser field `password` is what DATABASE.md §2.1 calls
`password_hash` — same column, Django's built-in name; renaming it would break
`set_password`/`check_password`/admin login for no real benefit, so this file
keeps Django's name and notes the mapping here instead.
"""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models


def _default_risk_policy() -> dict:
    # "dangerous" can never be "auto" — SOUL.md §15.2 / SECURITY.md §4. This
    # is the platform default; PermissionProfile.save() enforces the
    # invariant can't be violated even by a workspace-specific profile.
    return {"safe": "auto", "sensitive": "approval", "dangerous": "approval"}


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(UUIDPrimaryKeyModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    # Envelope-encrypted TOTP shared secret (core.encryption), set during
    # enrollment and only "live" once mfa_enabled flips to True on confirm.
    # Added in Milestone 1 — see DATABASE.md §2.1 note.
    mfa_secret = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Required by Django's admin/auth machinery; not part of DATABASE.md's
    # product schema, but necessary for AbstractBaseUser + the admin site.
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.email


class OAuthIdentity(UUIDPrimaryKeyModel):
    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        GITHUB = "github", "GitHub"
        MICROSOFT = "microsoft", "Microsoft"
        SAML = "saml", "SAML"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="oauth_identities")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_user_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "oauth_identities"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"], name="uniq_oauth_provider_identity"
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_user_id}"


class Workspace(UUIDPrimaryKeyModel):
    class WorkspaceType(models.TextChoices):
        PERSONAL = "personal", "Personal"
        ORGANIZATION = "organization", "Organization"

    class PlanTier(models.TextChoices):
        SELF_HOSTED_FREE = "self_hosted_free", "Self-hosted (free)"
        CLOUD_FREE = "cloud_free", "Cloud (free)"
        CLOUD_PRO = "cloud_pro", "Cloud (pro)"
        CLOUD_ENTERPRISE = "cloud_enterprise", "Cloud (enterprise)"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=WorkspaceType.choices)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_workspaces")
    plan_tier = models.CharField(
        max_length=20, choices=PlanTier.choices, default=PlanTier.SELF_HOSTED_FREE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspaces"

    def __str__(self) -> str:
        return self.name


class WorkspaceMember(UUIDPrimaryKeyModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        GUEST = "guest", "Guest"
        SECURITY_ADMIN = "security_admin", "Security admin"
        BILLING_ADMIN = "billing_admin", "Billing admin"
        DEVELOPER_ADMIN = "developer_admin", "Developer admin"
        AUDITOR = "auditor", "Auditor"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="workspace_memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workspace_members"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="uniq_workspace_member")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.workspace_id} ({self.role})"


class ProviderCredential(UUIDPrimaryKeyModel):
    """Per DATABASE.md §2.7. `deployment_mode` is currently always DEEPSEEK_CLOUD —
    DEEPSEEK_SELF_HOSTED is a reserved value for the adapter planned in SOUL.md §16.2,
    not usable until that ships (enforced in the serializer, not here)."""

    class DeploymentMode(models.TextChoices):
        DEEPSEEK_CLOUD = "deepseek_cloud", "DeepSeek Cloud"
        DEEPSEEK_SELF_HOSTED = "deepseek_self_hosted", "DeepSeek Self-Hosted"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="provider_credentials"
    )
    deployment_mode = models.CharField(max_length=30, choices=DeploymentMode.choices)
    encrypted_key = models.BinaryField(null=True, blank=True)
    endpoint_url = models.URLField(null=True, blank=True)
    label = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "provider_credentials"

    def __str__(self) -> str:
        return f"{self.label} ({self.deployment_mode})"


class PermissionProfile(UUIDPrimaryKeyModel):
    """Per DATABASE.md §2.3. Milestone 3 scope: a data container with a
    sensible default, not yet actively enforced anywhere — coworkers can't
    call tools until Milestone 4 wires up real execution + the approval
    gate (SECURITY.md §4). `org_policy_floors` (the "coworker config can't
    loosen this" guarantee) also lands with that milestone."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="permission_profiles",
        help_text="Null = platform default profile, per DATABASE.md §2.3.",
    )
    name = models.CharField(max_length=255)
    default_tool_risk_policy = models.JSONField(default=_default_risk_policy)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "permission_profiles"

    def save(self, *args, **kwargs):
        if self.default_tool_risk_policy.get("dangerous") == "auto":
            raise ValidationError(
                "default_tool_risk_policy['dangerous'] can never be 'auto' — SOUL.md §15.2."
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Coworker(UUIDPrimaryKeyModel):
    """Per DATABASE.md §2.2. Identity/status only — versioned attributes
    (role_description, model_binding, permission_profile) live on
    CoworkerVersion, per the doc's split between "stable identity" and
    "what can change and be rolled back."""

    class OwnerType(models.TextChoices):
        USER = "user", "User"
        TEAM = "team", "Team"
        ORGANIZATION = "organization", "Organization"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="coworkers")
    owner_type = models.CharField(
        max_length=20, choices=OwnerType.choices, default=OwnerType.USER
    )
    # Polymorphic per DATABASE.md §2.2 — no FK, since `team`/`organization`
    # aren't real models until Teams/Organizations land (V2). Only `user` is
    # usable right now; enforced in the serializer, not here, same pattern
    # as ai.models.ModelCall.coworker_id in Milestone 2.
    owner_id = models.UUIDField()
    name = models.CharField(max_length=255)
    # TextField, not URLField: uploaded avatars are stored inline as data
    # URIs (self-contained for self-hosted deployments — no public object
    # storage URL to mint or expire).
    avatar_url = models.TextField(null=True, blank=True)
    current_version = models.ForeignKey(
        "CoworkerVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "coworkers"

    def __str__(self) -> str:
        return self.name


class CoworkerVersion(UUIDPrimaryKeyModel):
    coworker = models.ForeignKey(Coworker, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    role_description = models.TextField()
    model_binding = models.JSONField()
    permission_profile = models.ForeignKey(
        PermissionProfile, on_delete=models.PROTECT, related_name="coworker_versions"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    changelog = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "coworker_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["coworker", "version_number"], name="uniq_coworker_version_number"
            )
        ]
        ordering = ["-version_number"]

    def __str__(self) -> str:
        return f"{self.coworker_id} v{self.version_number}"


class Tool(UUIDPrimaryKeyModel):
    """Per DATABASE.md §2.3. Platform-wide catalog, not workspace-scoped."""

    class RiskClassification(models.TextChoices):
        SAFE = "safe", "Safe"
        SENSITIVE = "sensitive", "Sensitive"
        DANGEROUS = "dangerous", "Dangerous"

    class Provider(models.TextChoices):
        BUILT_IN = "built_in", "Built-in"
        SKILL_BUNDLED = "skill_bundled", "Skill-bundled"
        INTEGRATION = "integration", "Integration"

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    risk_classification = models.CharField(max_length=20, choices=RiskClassification.choices)
    input_schema = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.BUILT_IN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tools"

    def __str__(self) -> str:
        return self.name


class CoworkerToolAttachment(UUIDPrimaryKeyModel):
    coworker = models.ForeignKey(
        Coworker, on_delete=models.CASCADE, related_name="tool_attachments"
    )
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="coworker_attachments")
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coworker_tool_attachments"
        constraints = [
            models.UniqueConstraint(fields=["coworker", "tool"], name="uniq_coworker_tool")
        ]

    def __str__(self) -> str:
        return f"{self.coworker_id} -> {self.tool.name}"


class ApprovalRequest(UUIDPrimaryKeyModel):
    """Per DATABASE.md §2.3 approval_requests row. Exactly one of
    task_id / workflow_run_step_id / message_id is populated per row,
    depending on what triggered the tool call needing approval.

    All four "what triggered this" references are plain UUID fields, not
    FKs: Task and WorkflowRunStep don't exist as models yet (ARCHITECTURE.md
    §6 engine isn't built), and conversation_id/message_id are left the same
    way to avoid a circular import (ai.models already imports core.models,
    so core.models can't import ai.models back) — same polymorphic-reference
    pattern as Coworker.owner_id.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        EXPIRED = "expired", "Expired"

    task_id = models.UUIDField(null=True, blank=True)
    workflow_run_step_id = models.UUIDField(null=True, blank=True)
    conversation_id = models.UUIDField(null=True, blank=True)
    message_id = models.UUIDField(null=True, blank=True)
    coworker = models.ForeignKey(
        Coworker, on_delete=models.CASCADE, related_name="approval_requests"
    )
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="approval_requests")
    requested_action = models.JSONField(default=dict, blank=True)
    # Coworker-supplied plain-English headline ("Refund $214.00 across 3
    # Stripe charges") and justification for the approval surfaces. Both are
    # best-effort: blank whenever generation wasn't possible, and every UI
    # must fall back to tool_name + requested_action.
    summary = models.TextField(blank=True, default="")
    rationale = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "approval_requests"

    def __str__(self) -> str:
        return f"{self.tool.name} for {self.coworker_id} ({self.status})"


class ApprovalPolicy(UUIDPrimaryKeyModel):
    """A standing "always allow" rule a human creates from an approval
    decision ("Always allow refunds under $250"): auto-approves a tool for
    one coworker — or any coworker when coworker is null — instead of
    asking every time. Optionally conditioned on one numeric argument
    staying at or under a threshold; a policy with a condition matches
    fail-closed (missing or non-numeric argument means no match).

    Org policy floors always win: enforcement consults policies only when
    no organization floor forces approval for the tool's risk tier, so a
    workspace member cannot use a policy to bypass governance.
    """

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="approval_policies"
    )
    coworker = models.ForeignKey(
        Coworker,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
    )
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="approval_policies")
    # Dot-path into the tool-call arguments (e.g. "amount" or
    # "refund.total"); set together with max_amount, or both empty for a
    # blanket allow.
    argument_path = models.CharField(max_length=255, blank=True, default="")
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "approval_policies"

    def __str__(self) -> str:
        scope = self.coworker_id or "any coworker"
        condition = (
            f"{self.argument_path} <= {self.max_amount}" if self.argument_path else "always"
        )
        return f"allow {self.tool.name} for {scope} ({condition})"


class AuditLog(UUIDPrimaryKeyModel):
    """Per DATABASE.md §2.3 / SECURITY.md §4 — append-only. No update or
    delete path exists anywhere in application code; rows are written once
    by core.interface.write_audit_log and never touched again."""

    class ActorType(models.TextChoices):
        USER = "user", "User"
        COWORKER = "coworker", "Coworker"
        SYSTEM = "system", "System"

    # Nullable — DATABASE.md §2.3 doesn't mark it so, but not every actor/event
    # is meaningfully scoped to one workspace (e.g. a login event for a user
    # who owns no workspace of their own, only guest memberships elsewhere).
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs"
    )
    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=255)
    resource_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        indexes = [models.Index(fields=["workspace", "created_at"])]

    def __str__(self) -> str:
        return f"{self.actor_type}:{self.actor_id} {self.action} {self.resource_type}"


class Task(UUIDPrimaryKeyModel):
    class CreatedByType(models.TextChoices):
        USER = "user", "User"
        COWORKER = "coworker", "Coworker"
        WORKFLOW = "workflow", "Workflow"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"
        BLOCKED = "blocked", "Blocked"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="tasks")
    project_id = models.UUIDField(null=True, blank=True)
    coworker = models.ForeignKey(Coworker, on_delete=models.CASCADE, related_name="tasks")
    created_by_type = models.CharField(max_length=20, choices=CreatedByType.choices)
    created_by_id = models.UUIDField()
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    due_at = models.DateTimeField(null=True, blank=True)
    parent_task = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="subtasks"
    )
    # Durable orchestration state makes Celery retries/resumes independent of
    # any one worker process. `result` is the user-facing final answer.
    execution_state = models.JSONField(default=dict, blank=True)
    result = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tasks"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["workspace", "status"], name="tasks_workspac_47cb9b_idx"
            )
        ]


class Notification(UUIDPrimaryKeyModel):
    class Type(models.TextChoices):
        TASK_COMPLETED = "task_completed", "Task completed"
        APPROVAL_REQUESTED = "approval_requested", "Approval requested"
        WORKFLOW_FAILED = "workflow_failed", "Workflow failed"
        RESEARCH_COMPLETED = "research_completed", "Research completed"
        WEBSITE_CHANGED = "website_changed", "Website changed"
        MONITOR_FAILED = "monitor_failed", "Website monitor failed"
        MENTION = "mention", "Mention"
        BILLING = "billing", "Billing"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="notifications"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30, choices=Type.choices)
    payload = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "read_at", "created_at"],
                name="notificatio_user_id_ee8d09_idx",
            )
        ]


# ---------------------------------------------------------------------------
# Phase 2 / V2: organizations, Agent Teams, workflows, marketplace and SDK.


class OrgPolicyFloor(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="policy_floors")
    tool_risk_classification = models.CharField(
        max_length=20, choices=Tool.RiskClassification.choices
    )
    min_required_policy = models.CharField(max_length=20, default="approval")
    enforced = models.BooleanField(default=True)

    class Meta:
        db_table = "org_policy_floors"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "tool_risk_classification"], name="uniq_org_policy_floor"
            )
        ]


class Team(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="human_teams")
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "teams"
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="uniq_team_name")]


class TeamMember(UUIDPrimaryKeyModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="human_team_memberships")
    role = models.CharField(max_length=20, choices=WorkspaceMember.Role.choices)

    class Meta:
        db_table = "team_members"
        constraints = [models.UniqueConstraint(fields=["team", "user"], name="uniq_team_member")]


class AgentTeam(UUIDPrimaryKeyModel):
    class CollaborationPattern(models.TextChoices):
        SEQUENTIAL = "sequential", "Sequential"
        MANAGER_DELEGATE = "manager_delegate", "Manager/delegate"
        PARALLEL_MERGE = "parallel_merge", "Parallel/merge"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="agent_teams")
    name = models.CharField(max_length=255)
    collaboration_pattern = models.CharField(max_length=30, choices=CollaborationPattern.choices)
    current_version = models.ForeignKey(
        "AgentTeamVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_teams"


class AgentTeamVersion(UUIDPrimaryKeyModel):
    agent_team = models.ForeignKey(AgentTeam, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_team_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["agent_team", "version_number"], name="uniq_agent_team_version"
            )
        ]


class AgentTeamMember(UUIDPrimaryKeyModel):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        RESEARCHER = "researcher", "Researcher"
        WRITER = "writer", "Writer"
        REVIEWER = "reviewer", "Reviewer"
        DEVELOPER = "developer", "Developer"
        TESTER = "tester", "Tester"
        SECURITY_REVIEWER = "security_reviewer", "Security reviewer"
        ARCHITECT = "architect", "Architect"
        PLANNER = "planner", "Planner"
        PRODUCT_MANAGER = "product_manager", "Product manager"
        CUSTOM = "custom", "Custom"

    agent_team_version = models.ForeignKey(
        AgentTeamVersion, on_delete=models.CASCADE, related_name="members"
    )
    coworker = models.ForeignKey(Coworker, on_delete=models.CASCADE, related_name="agent_team_memberships")
    role = models.CharField(max_length=30, choices=Role.choices)
    custom_role_label = models.CharField(max_length=100, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "agent_team_members"
        constraints = [
            models.UniqueConstraint(
                fields=["agent_team_version", "coworker"], name="uniq_agent_team_member"
            )
        ]
        ordering = ["position", "id"]


class AgentTeamRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    agent_team = models.ForeignKey(AgentTeam, on_delete=models.CASCADE, related_name="runs")
    version = models.ForeignKey(AgentTeamVersion, on_delete=models.PROTECT, related_name="runs")
    objective = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    result = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_team_runs"


class Project(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects"


class ProjectResource(UUIDPrimaryKeyModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="resources")
    resource_type = models.CharField(max_length=30)
    resource_id = models.UUIDField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_resources"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "resource_type", "resource_id"], name="uniq_project_resource"
            )
        ]


class MarketplaceListing(UUIDPrimaryKeyModel):
    class ListingType(models.TextChoices):
        SKILL = "skill", "Skill"
        CAPABILITY_PACK = "capability_pack", "Capability pack"
        WORKFLOW_TEMPLATE = "workflow_template", "Workflow template"
        TOOL = "tool", "Tool"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        UNLISTED = "unlisted", "Unlisted"
        ORG_PRIVATE = "org_private", "Organization private"

    class PricingModel(models.TextChoices):
        FREE = "free", "Free"
        PAID = "paid", "Paid"
        PAY_WHAT_YOU_WANT = "pay_what_you_want", "Pay what you want"

    publisher_workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="marketplace_listings"
    )
    listing_type = models.CharField(max_length=30, choices=ListingType.choices)
    name = models.CharField(max_length=255)
    summary = models.TextField()
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    pricing_model = models.CharField(max_length=30, choices=PricingModel.choices, default=PricingModel.FREE)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    verified_publisher = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marketplace_listings"


class MarketplaceListingVersion(UUIDPrimaryKeyModel):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    listing = models.ForeignKey(MarketplaceListing, on_delete=models.CASCADE, related_name="versions")
    version_string = models.CharField(max_length=50)
    manifest = models.JSONField(default=dict)
    changelog = models.TextField(blank=True)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "marketplace_listing_versions"
        constraints = [
            models.UniqueConstraint(fields=["listing", "version_string"], name="uniq_listing_version")
        ]


class SkillVersion(UUIDPrimaryKeyModel):
    listing_version = models.OneToOneField(
        MarketplaceListingVersion, on_delete=models.CASCADE, related_name="skill"
    )
    instruction_content = models.TextField()
    declared_tools = models.JSONField(default=list)
    dependencies = models.JSONField(default=list)

    class Meta:
        db_table = "skill_versions"


class CoworkerSkillAttachment(UUIDPrimaryKeyModel):
    coworker = models.ForeignKey(Coworker, on_delete=models.CASCADE, related_name="skill_attachments")
    skill = models.ForeignKey(SkillVersion, on_delete=models.CASCADE, related_name="coworker_attachments")
    enabled = models.BooleanField(default=True)
    attached_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coworker_skill_attachments"
        constraints = [models.UniqueConstraint(fields=["coworker", "skill"], name="uniq_coworker_skill")]


class MarketplaceInstall(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="marketplace_installs")
    listing_version = models.ForeignKey(
        MarketplaceListingVersion, on_delete=models.PROTECT, related_name="installs"
    )
    installed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    forked_from_listing_version = models.ForeignKey(
        MarketplaceListingVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="forks"
    )
    installed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marketplace_installs"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "listing_version"], name="uniq_marketplace_install")
        ]


class MarketplaceReview(UUIDPrimaryKeyModel):
    listing = models.ForeignKey(MarketplaceListing, on_delete=models.CASCADE, related_name="reviews")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="marketplace_reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="marketplace_reviews")
    rating = models.PositiveSmallIntegerField()
    review_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marketplace_reviews"
        constraints = [
            models.UniqueConstraint(fields=["listing", "workspace", "user"], name="uniq_listing_review")
        ]


class Workflow(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="workflows")
    name = models.CharField(max_length=255)
    current_version = models.ForeignKey(
        "WorkflowVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    marketplace_listing = models.ForeignKey(
        MarketplaceListing, on_delete=models.SET_NULL, null=True, blank=True, related_name="workflows"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workflows"


class WorkflowVersion(UUIDPrimaryKeyModel):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workflow_versions"
        constraints = [
            models.UniqueConstraint(fields=["workflow", "version_number"], name="uniq_workflow_version")
        ]


class WorkflowTrigger(UUIDPrimaryKeyModel):
    class TriggerType(models.TextChoices):
        MANUAL = "manual", "Manual"
        SCHEDULED = "scheduled", "Scheduled"
        EVENT = "event", "Event"

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="triggers")
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices)
    schedule_cron = models.CharField(max_length=100, null=True, blank=True)
    event_source = models.CharField(max_length=100, null=True, blank=True)
    enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_triggers"


class WorkflowRun(UUIDPrimaryKeyModel):
    class TriggeredBy(models.TextChoices):
        USER = "user", "User"
        SCHEDULE = "schedule", "Schedule"
        EVENT = "event", "Event"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    workflow_version = models.ForeignKey(WorkflowVersion, on_delete=models.PROTECT, related_name="runs")
    triggered_by = models.CharField(max_length=20, choices=TriggeredBy.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    current_step_index = models.PositiveIntegerField(default=0)
    context = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_runs"
        ordering = ["-started_at"]


class WorkflowRunStep(UUIDPrimaryKeyModel):
    class StepType(models.TextChoices):
        COWORKER_ACTION = "coworker_action", "Coworker action"
        TOOL_CALL = "tool_call", "Tool call"
        HUMAN_CHECKPOINT = "human_checkpoint", "Human checkpoint"
        CONDITION = "condition", "Condition"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    workflow_run = models.ForeignKey(WorkflowRun, on_delete=models.CASCADE, related_name="steps")
    step_index = models.PositiveIntegerField()
    step_type = models.CharField(max_length=30, choices=StepType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    definition = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_run_steps"
        constraints = [
            models.UniqueConstraint(fields=["workflow_run", "step_index"], name="uniq_workflow_run_step")
        ]
        ordering = ["step_index"]


class Integration(UUIDPrimaryKeyModel):
    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        CALENDAR = "calendar", "Calendar"
        SLACK = "slack", "Slack"
        DISCORD = "discord", "Discord"
        GITHUB = "github", "GitHub"
        TWITTER = "twitter", "Twitter / X"
        WEBHOOK = "webhook", "Generic webhook"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="integrations")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    name = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)
    encrypted_secret = models.BinaryField(null=True, blank=True)
    workspace_token = models.CharField(max_length=128, unique=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "integrations"


class ApiToken(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="api_tokens")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=255)
    token_prefix = models.CharField(max_length=20)
    token_hash = models.CharField(max_length=128, unique=True)
    scopes = models.JSONField(default=list)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_tokens"


class Subscription(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELLED = "cancelled", "Cancelled"

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="subscription")
    plan_tier = models.CharField(max_length=20, choices=Workspace.PlanTier.choices)
    seats = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    renews_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscriptions"


# ---------------------------------------------------------------------------
# Phase 3 / V3: enterprise identity/governance, economy and portability.


class EnterpriseSettings(UUIDPrimaryKeyModel):
    class DataRegion(models.TextChoices):
        US = "us", "United States"
        EU = "eu", "European Union"
        UK = "uk", "United Kingdom"
        CA = "ca", "Canada"
        AU = "au", "Australia"
        SELF_HOSTED = "self_hosted", "Self-hosted"

    class SupportTier(models.TextChoices):
        COMMUNITY = "community", "Community"
        STANDARD = "standard", "Standard"
        PREMIUM = "premium", "Premium"
        DEDICATED = "dedicated", "Dedicated"

    workspace = models.OneToOneField(
        Workspace, on_delete=models.CASCADE, related_name="enterprise_settings"
    )
    data_region = models.CharField(
        max_length=20, choices=DataRegion.choices, default=DataRegion.SELF_HOSTED
    )
    retention_days = models.PositiveIntegerField(default=30)
    legal_hold = models.BooleanField(default=False)
    support_tier = models.CharField(
        max_length=20, choices=SupportTier.choices, default=SupportTier.COMMUNITY
    )
    sla_uptime_percent = models.DecimalField(max_digits=5, decimal_places=3, default=99.500)
    sla_response_minutes = models.PositiveIntegerField(default=1440)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "enterprise_settings"


class SSOProvider(UUIDPrimaryKeyModel):
    class Protocol(models.TextChoices):
        SAML = "saml", "SAML 2.0"
        OIDC = "oidc", "OpenID Connect"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="sso_providers")
    name = models.CharField(max_length=255)
    protocol = models.CharField(max_length=10, choices=Protocol.choices)
    issuer = models.CharField(max_length=500)
    sso_url = models.URLField()
    entity_id = models.CharField(max_length=500, blank=True)
    client_id = models.CharField(max_length=255, blank=True)
    encrypted_secret = models.BinaryField(null=True, blank=True)
    email_domains = models.JSONField(default=list)
    attribute_mapping = models.JSONField(default=dict, blank=True)
    jit_provisioning = models.BooleanField(default=True)
    enforce_sso = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sso_providers"


class SCIMToken(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="scim_tokens")
    name = models.CharField(max_length=255)
    token_prefix = models.CharField(max_length=20)
    token_hash = models.CharField(max_length=128, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scim_tokens"


class OrganizationPolicyRule(UUIDPrimaryKeyModel):
    class Effect(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"
        REQUIRE_APPROVAL = "require_approval", "Require approval"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="policy_rules")
    name = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    conditions = models.JSONField(default=dict, blank=True)
    effect = models.CharField(max_length=30, choices=Effect.choices)
    priority = models.IntegerField(default=100)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization_policy_rules"
        ordering = ["priority", "created_at"]


class AuditAnomaly(UUIDPrimaryKeyModel):
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="audit_anomalies")
    anomaly_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    summary = models.TextField()
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "audit_anomalies"
        ordering = ["-detected_at"]


class ComplianceExport(UUIDPrimaryKeyModel):
    class ExportType(models.TextChoices):
        AUDIT = "audit", "Audit log"
        ACCESS = "access", "Access review"
        SOC2 = "soc2", "SOC 2 evidence"
        FULL = "full", "Full evidence bundle"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="compliance_exports")
    export_type = models.CharField(max_length=20, choices=ExportType.choices)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    evidence = models.JSONField(default=dict)
    checksum = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compliance_exports"


class MarketplaceSecurityReview(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PASSED = "passed", "Passed"
        NEEDS_REVIEW = "needs_review", "Needs review"
        FAILED = "failed", "Failed"

    listing_version = models.OneToOneField(
        MarketplaceListingVersion, on_delete=models.CASCADE, related_name="security_review"
    )
    score = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices)
    findings = models.JSONField(default=list)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marketplace_security_reviews"


class MarketplaceOrder(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="marketplace_orders")
    listing_version = models.ForeignKey(
        MarketplaceListingVersion, on_delete=models.PROTECT, related_name="orders"
    )
    buyer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marketplace_orders")
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "marketplace_orders"


class PayoutAccount(UUIDPrimaryKeyModel):
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="payout_account")
    provider = models.CharField(max_length=50, default="external")
    provider_account_id = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payout_accounts"


class MarketplacePayout(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    publisher_workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="marketplace_payouts"
    )
    listing = models.ForeignKey(MarketplaceListing, on_delete=models.CASCADE, related_name="payouts")
    order = models.OneToOneField(MarketplaceOrder, on_delete=models.PROTECT, related_name="payout")
    gross_usd = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee_usd = models.DecimalField(max_digits=10, decimal_places=2)
    net_payout_usd = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "marketplace_payouts"


class Artifact(UUIDPrimaryKeyModel):
    class ArtifactType(models.TextChoices):
        PRESENTATION = "presentation", "Presentation"
        DIAGRAM = "diagram", "Diagram"
        VIDEO_ANALYSIS = "video_analysis", "Video analysis"
        COWORKER_BUNDLE = "coworker_bundle", "Coworker bundle"
        COMPLIANCE = "compliance", "Compliance evidence"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="artifacts")
    artifact_type = models.CharField(max_length=30, choices=ArtifactType.choices)
    name = models.CharField(max_length=255)
    content = models.JSONField(default=dict)
    checksum = models.CharField(max_length=128)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="artifacts")
    source_coworker = models.ForeignKey(
        Coworker, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "artifacts"


# ---------------------------------------------------------------------------
# Phase 4: adaptive capability growth, memory negotiation, consensus and voice.


class CapabilityProposal(UUIDPrimaryKeyModel):
    class ProposedByType(models.TextChoices):
        COWORKER = "coworker", "Coworker"
        USER = "user", "User"

    class TargetType(models.TextChoices):
        TOOL = "tool", "Tool"
        SKILL = "skill", "Skill"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="capability_proposals"
    )
    coworker = models.ForeignKey(
        Coworker, on_delete=models.CASCADE, related_name="capability_proposals"
    )
    proposed_by_type = models.CharField(
        max_length=20, choices=ProposedByType.choices, default=ProposedByType.COWORKER
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_id = models.UUIDField()
    target_name = models.CharField(max_length=255)
    rationale = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_capability_proposals"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "capability_proposals"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "status"])]


class MemoryConflict(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    class ResolutionStrategy(models.TextChoices):
        KEEP_LEFT = "keep_left", "Keep first memory"
        KEEP_RIGHT = "keep_right", "Keep second memory"
        MERGE = "merge", "Merge"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="memory_conflicts"
    )
    left_memory_id = models.UUIDField()
    right_memory_id = models.UUIDField()
    subject = models.CharField(max_length=255)
    left_content = models.TextField()
    right_content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolution_strategy = models.CharField(
        max_length=20, choices=ResolutionStrategy.choices, blank=True
    )
    resolved_content = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_memory_conflicts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "memory_conflicts"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "left_memory_id", "right_memory_id"],
                name="uniq_memory_conflict_pair",
            )
        ]


class ConsensusSession(UUIDPrimaryKeyModel):
    class Method(models.TextChoices):
        MAJORITY = "majority", "Majority"
        UNANIMOUS = "unanimous", "Unanimous"
        CONFIDENCE_WEIGHTED = "confidence_weighted", "Confidence weighted"

    class Status(models.TextChoices):
        COLLECTING = "collecting", "Collecting"
        DECIDED = "decided", "Decided"
        DEADLOCKED = "deadlocked", "Deadlocked"

    agent_team = models.ForeignKey(
        AgentTeam, on_delete=models.CASCADE, related_name="consensus_sessions"
    )
    question = models.TextField()
    options = models.JSONField(default=list)
    method = models.CharField(max_length=30, choices=Method.choices, default=Method.MAJORITY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COLLECTING)
    result_option = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "consensus_sessions"
        ordering = ["-created_at"]


class ConsensusVote(UUIDPrimaryKeyModel):
    session = models.ForeignKey(
        ConsensusSession, on_delete=models.CASCADE, related_name="votes"
    )
    coworker = models.ForeignKey(Coworker, on_delete=models.CASCADE, related_name="consensus_votes")
    task = models.OneToOneField(
        Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="consensus_vote"
    )
    option = models.CharField(max_length=255)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=1)
    rationale = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consensus_votes"
        constraints = [
            models.UniqueConstraint(fields=["session", "coworker"], name="uniq_consensus_vote")
        ]


class VoiceSession(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="voice_sessions")
    coworker = models.ForeignKey(Coworker, on_delete=models.CASCADE, related_name="voice_sessions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="voice_sessions")
    conversation_id = models.UUIDField()
    language = models.CharField(max_length=20, default="en-US")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "voice_sessions"
        ordering = ["-started_at"]


class VoiceTurn(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        COMPLETE = "complete", "Complete"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"
        FAILED = "failed", "Failed"

    session = models.ForeignKey(VoiceSession, on_delete=models.CASCADE, related_name="turns")
    user_transcript = models.TextField()
    assistant_transcript = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    approval_request_id = models.UUIDField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "voice_turns"
        ordering = ["created_at"]
