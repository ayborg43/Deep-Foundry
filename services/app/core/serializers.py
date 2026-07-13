from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.encryption import decrypt_from_bytes, mask_secret
from core.models import ProviderCredential, User, Workspace


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

    def validate_deployment_mode(self, value: str) -> str:
        if value != ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD:
            raise serializers.ValidationError(
                "Only 'deepseek_cloud' is usable until the self-hosted adapter ships "
                "(SOUL.md §16.2)."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        if self.instance is None and not attrs.get("api_key"):
            raise serializers.ValidationError({"api_key": "This field is required."})
        return attrs


class MFAEnrollConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6)


class MFALoginVerifySerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(min_length=6, max_length=6)


class GoogleOAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.CharField()
