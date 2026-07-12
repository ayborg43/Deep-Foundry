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
from django.db import models


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
