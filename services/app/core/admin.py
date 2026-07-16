from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from ai.models import ModelCall
from core.models import (
    AgentTeam,
    AuditLog,
    Coworker,
    OAuthIdentity,
    ProviderCredential,
    Task,
    User,
    Workflow,
    Workspace,
    WorkspaceMember,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["email"]
    list_display = ["email", "display_name", "is_staff", "is_active"]
    search_fields = ["email", "display_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name", "avatar_url", "mfa_enabled")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "plan_tier", "owner", "created_at"]
    list_filter = ["type", "plan_tier"]
    search_fields = ["name", "owner__email"]
    raw_id_fields = ["owner"]


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ["user", "workspace", "role", "joined_at"]
    list_filter = ["role"]
    search_fields = ["user__email", "workspace__name"]
    raw_id_fields = ["user", "workspace", "invited_by"]


@admin.register(Coworker)
class CoworkerAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace", "owner_type", "status", "created_at"]
    list_filter = ["status", "owner_type"]
    search_fields = ["name", "workspace__name"]
    raw_id_fields = ["workspace", "current_version"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "workspace", "coworker", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "workspace__name"]
    raw_id_fields = ["workspace", "coworker"]
    date_hierarchy = "created_at"


@admin.register(AgentTeam)
class AgentTeamAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace", "collaboration_pattern", "created_at"]
    search_fields = ["name", "workspace__name"]
    raw_id_fields = ["workspace", "current_version"]


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace", "created_at"]
    search_fields = ["name", "workspace__name"]
    raw_id_fields = ["workspace", "current_version"]


@admin.register(ProviderCredential)
class ProviderCredentialAdmin(admin.ModelAdmin):
    # Never surface the encrypted key material through the admin.
    list_display = ["label", "workspace", "deployment_mode", "is_default", "created_at"]
    list_filter = ["deployment_mode", "is_default"]
    search_fields = ["label", "workspace__name"]
    raw_id_fields = ["workspace"]
    exclude = ["encrypted_key"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor_type", "action", "resource_type", "workspace"]
    list_filter = ["actor_type", "action"]
    search_fields = ["action", "resource_type", "workspace__name"]
    raw_id_fields = ["workspace"]
    date_hierarchy = "created_at"


@admin.register(ModelCall)
class ModelCallAdmin(admin.ModelAdmin):
    list_display = ["created_at", "workspace", "model_id", "input_tokens", "output_tokens", "cost_usd"]
    list_filter = ["deployment_mode", "fallback_used"]
    search_fields = ["model_id", "workspace__name"]
    raw_id_fields = ["workspace", "coworker"]
    date_hierarchy = "created_at"


admin.site.register(OAuthIdentity)
