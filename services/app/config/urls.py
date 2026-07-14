from django.contrib import admin
from django.urls import include, path
from core.admin_views import InternalAuditLogView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),  # /health at the root — IMPLEMENTATION_PLAN.md Milestone 0
    path("api/v1/", include("core.api_urls")),  # Milestone 1 — API.md §2
    path("internal/v1/audit-log", InternalAuditLogView.as_view(), name="internal-audit-log"),
]
