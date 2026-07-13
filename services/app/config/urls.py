from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),  # /health at the root — IMPLEMENTATION_PLAN.md Milestone 0
    path("api/v1/", include("core.api_urls")),  # Milestone 1 — API.md §2
]
