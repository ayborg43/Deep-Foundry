from django.urls import path

from research.views import (
    ResearchDomainPolicyView,
    ResearchRunDetailView,
    ResearchRunExportView,
    ResearchRunListCreateView,
    ResearchRunSourcesView,
    WebsiteMonitorDetailView,
    WebsiteMonitorHistoryView,
    WebsiteMonitorListCreateView,
    WebsiteMonitorRunNowView,
)

urlpatterns = [
    path("research-runs", ResearchRunListCreateView.as_view(), name="research-run-list-create"),
    path("research-runs/<uuid:run_id>", ResearchRunDetailView.as_view(), name="research-run-detail"),
    path(
        "research-runs/<uuid:run_id>/sources",
        ResearchRunSourcesView.as_view(),
        name="research-run-sources",
    ),
    path(
        "research-runs/<uuid:run_id>/exports/<str:export_format>",
        ResearchRunExportView.as_view(),
        name="research-run-export",
    ),
    path(
        "website-monitors",
        WebsiteMonitorListCreateView.as_view(),
        name="website-monitor-list-create",
    ),
    path(
        "website-monitors/<uuid:monitor_id>",
        WebsiteMonitorDetailView.as_view(),
        name="website-monitor-detail",
    ),
    path(
        "website-monitors/<uuid:monitor_id>/run",
        WebsiteMonitorRunNowView.as_view(),
        name="website-monitor-run",
    ),
    path(
        "website-monitors/<uuid:monitor_id>/history",
        WebsiteMonitorHistoryView.as_view(),
        name="website-monitor-history",
    ),
    path(
        "workspaces/<uuid:workspace_id>/research-policy",
        ResearchDomainPolicyView.as_view(),
        name="research-domain-policy",
    ),
]
