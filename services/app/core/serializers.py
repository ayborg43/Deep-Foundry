from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.encryption import decrypt_from_bytes, mask_secret
from core.models import (
    ApprovalRequest,
    Coworker,
    CoworkerToolAttachment,
    CoworkerVersion,
    ProviderCredential,
    Tool,
    User,
    Workspace,
)

# Keep this aligned with ai/model_router/adapters/deepseek_cloud.py.
VALID_DEEPSEEK_MODEL_IDS = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
}


def validate_model_binding_value(value: dict) -> dict:
    if not isinstance(value, dict) or not value.get("primary"):
        raise serializers.ValidationError("model_binding.primary is required.")
    primary = value["primary"]
    mode = value.get("deployment_mode", ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD)
    if mode not in ProviderCredential.DeploymentMode.values:
        raise serializers.ValidationError("Unknown deployment_mode.")
    if mode == ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD and primary not in VALID_DEEPSEEK_MODEL_IDS:
        raise serializers.ValidationError(
            f"Unknown model {primary!r}. Expected one of {sorted(VALID_DEEPSEEK_MODEL_IDS)}."
        )
    for fallback_id in value.get("fallback", []):
        if mode == ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD and fallback_id not in VALID_DEEPSEEK_MODEL_IDS:
            raise serializers.ValidationError(
                f"Unknown fallback model {fallback_id!r}. "
                f"Expected one of {sorted(VALID_DEEPSEEK_MODEL_IDS)}."
            )
    return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "display_name", "avatar_url", "mfa_enabled", "created_at"]
        read_only_fields = ["id", "email", "mfa_enabled", "created_at"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    display_name = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_email(self, value: str) -> str:
        value = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class WorkspaceSerializer(serializers.ModelSerializer):
    owner_id = serializers.UUIDField(source="owner.id", read_only=True)

    class Meta:
        model = Workspace
        fields = ["id", "name", "type", "plan_tier", "owner_id", "created_at"]
        read_only_fields = ["id", "type", "plan_tier", "owner_id", "created_at"]


class ProviderCredentialSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False)
    masked_key = serializers.SerializerMethodField()

    class Meta:
        model = ProviderCredential
        fields = [
            "id",
            "label",
            "deployment_mode",
            "api_key",
            "endpoint_url",
            "masked_key",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "masked_key", "created_at"]

    def get_masked_key(self, obj: ProviderCredential) -> str | None:
        if not obj.encrypted_key:
            return None
        # Decrypted only transiently, for masking — the plaintext never leaves
        # this method, per SECURITY.md §6.
        return mask_secret(decrypt_from_bytes(bytes(obj.encrypted_key)))

    def validate(self, attrs: dict) -> dict:
        mode = attrs.get("deployment_mode", getattr(self.instance, "deployment_mode", None))
        if self.instance is None and mode == ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD and not attrs.get("api_key"):
            raise serializers.ValidationError({"api_key": "This field is required for DeepSeek Cloud."})
        if mode == ProviderCredential.DeploymentMode.DEEPSEEK_SELF_HOSTED and not attrs.get("endpoint_url"):
            raise serializers.ValidationError({"endpoint_url": "This field is required for self-hosted DeepSeek."})
        return attrs


class MFAEnrollConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6)


class MFALoginVerifySerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(min_length=6, max_length=6)


class GoogleOAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.CharField()


class ToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        fields = [
            "id",
            "name",
            "description",
            "risk_classification",
            "input_schema",
            "output_schema",
            "provider",
            "created_at",
        ]
        read_only_fields = fields


class CoworkerToolAttachmentSerializer(serializers.ModelSerializer):
    tool = ToolSerializer(read_only=True)
    tool_id = serializers.PrimaryKeyRelatedField(
        queryset=Tool.objects.all(), source="tool", write_only=True
    )

    class Meta:
        model = CoworkerToolAttachment
        fields = ["id", "tool", "tool_id", "config", "enabled", "created_at"]
        read_only_fields = ["id", "tool", "created_at"]


class CoworkerVersionSerializer(serializers.ModelSerializer):
    created_by_id = serializers.UUIDField(
        source="created_by.id", read_only=True, allow_null=True, default=None
    )
    permission_profile = serializers.SerializerMethodField()

    class Meta:
        model = CoworkerVersion
        fields = [
            "id",
            "version_number",
            "role_description",
            "model_binding",
            "permission_profile",
            "created_by_id",
            "created_at",
            "changelog",
        ]
        read_only_fields = fields

    def get_permission_profile(self, obj: CoworkerVersion) -> dict:
        return obj.permission_profile.default_tool_risk_policy


class CoworkerSerializer(serializers.ModelSerializer):
    """Flattens the active CoworkerVersion's attributes to the top level, per
    API.md §3's illustrative Coworker response shape. Reusable Skills belong to
    the V2 SDK/Marketplace; `attached_tools` is the MVP capability attachment."""

    role_description = serializers.SerializerMethodField()
    model_binding = serializers.SerializerMethodField()
    permission_profile = serializers.SerializerMethodField()
    current_version = serializers.SerializerMethodField()
    attached_tools = serializers.SerializerMethodField()

    class Meta:
        model = Coworker
        fields = [
            "id",
            "name",
            "avatar_url",
            "owner_type",
            "owner_id",
            "role_description",
            "model_binding",
            "permission_profile",
            "attached_tools",
            "status",
            "current_version",
            "created_at",
        ]
        read_only_fields = ["id", "status", "current_version", "created_at"]

    def get_role_description(self, obj: Coworker) -> str:
        return obj.current_version.role_description if obj.current_version else ""

    def get_model_binding(self, obj: Coworker) -> dict:
        return obj.current_version.model_binding if obj.current_version else {}

    def get_permission_profile(self, obj: Coworker) -> dict:
        if not obj.current_version:
            return {}
        return obj.current_version.permission_profile.default_tool_risk_policy

    def get_current_version(self, obj: Coworker) -> int | None:
        return obj.current_version.version_number if obj.current_version else None

    def get_attached_tools(self, obj: Coworker) -> list[dict]:
        return [
            {"id": str(a.tool_id), "name": a.tool.name, "enabled": a.enabled}
            for a in obj.tool_attachments.select_related("tool").all()
        ]


class CoworkerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    avatar_url = serializers.URLField(required=False, allow_null=True)
    role_description = serializers.CharField()
    model_binding = serializers.JSONField()
    owner_type = serializers.ChoiceField(
        choices=Coworker.OwnerType.choices, required=False, default=Coworker.OwnerType.USER
    )
    owner_id = serializers.UUIDField(required=False)

    def validate_model_binding(self, value: dict) -> dict:
        return validate_model_binding_value(value)


class CoworkerUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    avatar_url = serializers.URLField(required=False, allow_null=True)
    role_description = serializers.CharField(required=False)
    model_binding = serializers.JSONField(required=False)
    permission_profile = serializers.JSONField(required=False)
    changelog = serializers.CharField(required=False, allow_blank=True)

    def validate_model_binding(self, value: dict) -> dict:
        return validate_model_binding_value(value)

    def validate_permission_profile(self, value: dict) -> dict:
        if not isinstance(value, dict) or set(value) != {"safe", "sensitive", "dangerous"}:
            raise serializers.ValidationError(
                "Set a policy for each of safe, sensitive, and dangerous."
            )
        for level, policy in value.items():
            if policy not in ("auto", "approval"):
                raise serializers.ValidationError(f"{level} must be 'auto' or 'approval'.")
        # SOUL.md §15.2 / SECURITY.md §4 — dangerous tools always need a human.
        if value["dangerous"] == "auto":
            raise serializers.ValidationError(
                "Dangerous tools can never run automatically; they always need approval."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")
        return attrs


class ApprovalRequestSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)
    tool_risk_classification = serializers.CharField(
        source="tool.risk_classification", read_only=True
    )
    coworker_name = serializers.CharField(source="coworker.name", read_only=True)
    task_title = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            "id",
            "coworker_id",
            "tool_id",
            "tool_name",
            "tool_risk_classification",
            "coworker_name",
            "task_title",
            "conversation_id",
            "message_id",
            "task_id",
            "workflow_run_step_id",
            "requested_action",
            "summary",
            "rationale",
            "status",
            "decided_by",
            "decided_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_task_title(self, obj: ApprovalRequest) -> str | None:
        if not obj.task_id:
            return None
        from core.models import Task

        return Task.objects.filter(id=obj.task_id).values_list("title", flat=True).first()
