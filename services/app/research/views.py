from __future__ import annotations

import json
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.structured_extraction import extraction_to_csv
from core.interface import write_audit_log
from core.models import Coworker
from core.permissions import get_coworker_for_member, get_workspace_for_member
from core.v2_services import require_workspace_admin
from research.models import (
    ResearchDomainPolicy,
    ResearchRun,
    WebsiteMonitor,
    WebsiteMonitorRun,
)
from research.serializers import (
    ResearchDomainPolicySerializer,
    ResearchRunCreateSerializer,
    ResearchRunSerializer,
    ResearchRunSummarySerializer,
    ResearchSourceSerializer,
    WebsiteMonitorCreateSerializer,
    WebsiteMonitorRunSerializer,
    WebsiteMonitorSerializer,
)


def _workspace_coworker(request: Request, workspace, coworker_id):
    if not coworker_id:
        return None
    coworker = get_coworker_for_member(request.user, coworker_id)
    if coworker.workspace_id != workspace.id or coworker.status != Coworker.Status.ACTIVE:
        from rest_framework.exceptions import ValidationError

        raise ValidationError("The coworker must be active in this workspace.")
    return coworker


def _merged_controls(workspace, controls: dict) -> dict:
    policy = ResearchDomainPolicy.objects.filter(workspace=workspace).first()
    if policy is None:
        return controls
    merged = {**policy.default_controls, **controls}
    merged["trusted_domains"] = list(
        dict.fromkeys(policy.trusted_domains + controls.get("trusted_domains", []))
    )
    merged["blocked_domains"] = list(
        dict.fromkeys(policy.blocked_domains + controls.get("blocked_domains", []))
    )
    merged["trusted_domains"] = [
        value for value in merged["trusted_domains"] if value not in merged["blocked_domains"]
    ]
    return merged


class ResearchRunListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = (
            ResearchRun.objects.filter(workspace__members__user=request.user)
            .select_related("coworker")
            .annotate(source_count=Count("sources", distinct=True))
            .distinct()
        )
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id:
            get_workspace_for_member(request.user, workspace_id)
            queryset = queryset.filter(workspace_id=workspace_id)
        return Response(ResearchRunSummarySerializer(queryset[:100], many=True).data)

    def post(self, request: Request) -> Response:
        serializer = ResearchRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workspace = get_workspace_for_member(request.user, data["workspace_id"])
        coworker = _workspace_coworker(request, workspace, data.get("coworker_id"))
        controls = _merged_controls(workspace, data["controls"])
        with transaction.atomic():
            run = ResearchRun.objects.create(
                workspace=workspace,
                created_by=request.user,
                coworker=coworker,
                query=data["query"],
                mode=data["mode"],
                controls=controls,
            )
            write_audit_log(
                actor_type="user",
                actor_id=request.user.id,
                action="research.created",
                resource_type="research_run",
                resource_id=run.id,
                workspace_id=workspace.id,
                metadata={"mode": run.mode},
            )
            from worker.tasks import execute_research_run

            transaction.on_commit(lambda: execute_research_run.delay(str(run.id)))
        return Response(ResearchRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class ResearchRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request: Request, run_id: str) -> ResearchRun:
        run = get_object_or_404(
            ResearchRun.objects.select_related("coworker", "created_by").prefetch_related(
                "steps", "sources__evidence"
            ),
            id=run_id,
        )
        get_workspace_for_member(request.user, run.workspace_id)
        return run

    def get(self, request: Request, run_id: str) -> Response:
        return Response(ResearchRunSerializer(self._get(request, run_id)).data)

    def patch(self, request: Request, run_id: str) -> Response:
        run = self._get(request, run_id)
        if request.data.get("cancel") is not True:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"cancel": "Set cancel to true to stop this run."})
        if run.status not in {
            ResearchRun.Status.COMPLETED,
            ResearchRun.Status.FAILED,
            ResearchRun.Status.CANCELLED,
        }:
            run.cancel_requested = True
            run.save(update_fields=["cancel_requested", "updated_at"])
        return Response(ResearchRunSerializer(run).data)


class ResearchRunSourcesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id: str) -> Response:
        run = get_object_or_404(ResearchRun, id=run_id)
        get_workspace_for_member(request.user, run.workspace_id)
        return Response(
            ResearchSourceSerializer(
                run.sources.prefetch_related("evidence"), many=True
            ).data
        )


class ResearchRunExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id: str, export_format: str):
        run = get_object_or_404(ResearchRun, id=run_id)
        get_workspace_for_member(request.user, run.workspace_id)
        extraction = getattr(run, "extraction", None)
        if export_format == "csv":
            if extraction is None:
                return Response(
                    {"detail": "This research run has no structured extraction."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            response = HttpResponse(
                extraction_to_csv(extraction.data),
                content_type="text/csv; charset=utf-8",
            )
            response["Content-Disposition"] = f'attachment; filename="research-{run.id}.csv"'
            return response
        if export_format == "json":
            payload = {
                "id": str(run.id),
                "query": run.query,
                "report": run.report_markdown,
                "quality": {
                    "weak_evidence": run.weak_evidence,
                    "reasons": run.weak_evidence_reasons,
                    "conflicts": run.conflicts,
                },
                "extraction": extraction.data if extraction else None,
                "sources": ResearchSourceSerializer(
                    run.sources.prefetch_related("evidence"), many=True
                ).data,
            }
            response = HttpResponse(
                json.dumps(payload, indent=2, default=str),
                content_type="application/json",
            )
            response["Content-Disposition"] = f'attachment; filename="research-{run.id}.json"'
            return response
        if export_format == "markdown":
            response = HttpResponse(run.report_markdown, content_type="text/markdown; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="research-{run.id}.md"'
            return response
        return Response({"detail": "Use csv, json, or markdown."}, status=400)


class WebsiteMonitorListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = (
            WebsiteMonitor.objects.filter(workspace__members__user=request.user)
            .select_related("created_by", "coworker")
            .prefetch_related("runs__snapshot")
            .distinct()
        )
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id:
            get_workspace_for_member(request.user, workspace_id)
            queryset = queryset.filter(workspace_id=workspace_id)
        return Response(WebsiteMonitorSerializer(queryset[:100], many=True).data)

    def post(self, request: Request) -> Response:
        serializer = WebsiteMonitorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workspace = get_workspace_for_member(request.user, data["workspace_id"])
        coworker = _workspace_coworker(request, workspace, data.get("coworker_id"))
        interval = timedelta(
            days=7 if data["frequency"] == WebsiteMonitor.Frequency.WEEKLY else 1
        )
        monitor = WebsiteMonitor.objects.create(
            workspace=workspace,
            created_by=request.user,
            coworker=coworker,
            name=data["name"],
            url=data["url"],
            frequency=data["frequency"],
            enabled=data["enabled"],
            use_browser=data["use_browser"],
            crawl_pages=data["crawl_pages"],
            max_depth=data["max_depth"],
            controls=_merged_controls(workspace, data["controls"]),
            next_run_at=timezone.now() + interval,
        )
        return Response(
            WebsiteMonitorSerializer(monitor).data,
            status=status.HTTP_201_CREATED,
        )


class WebsiteMonitorDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request: Request, monitor_id: str) -> WebsiteMonitor:
        monitor = get_object_or_404(WebsiteMonitor, id=monitor_id)
        get_workspace_for_member(request.user, monitor.workspace_id)
        return monitor

    def get(self, request: Request, monitor_id: str) -> Response:
        return Response(WebsiteMonitorSerializer(self._get(request, monitor_id)).data)

    def patch(self, request: Request, monitor_id: str) -> Response:
        monitor = self._get(request, monitor_id)
        serializer = WebsiteMonitorCreateSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "workspace_id" in data and data["workspace_id"] != monitor.workspace_id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("A monitor cannot be moved to another workspace.")
        if "coworker_id" in data:
            monitor.coworker = _workspace_coworker(
                request, monitor.workspace, data["coworker_id"]
            )
        for field in (
            "name",
            "url",
            "frequency",
            "enabled",
            "use_browser",
            "crawl_pages",
            "max_depth",
        ):
            if field in data:
                setattr(monitor, field, data[field])
        if "controls" in data:
            monitor.controls = _merged_controls(monitor.workspace, data["controls"])
        monitor.save()
        return Response(WebsiteMonitorSerializer(monitor).data)

    def delete(self, request: Request, monitor_id: str) -> Response:
        monitor = self._get(request, monitor_id)
        monitor.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebsiteMonitorRunNowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, monitor_id: str) -> Response:
        monitor = get_object_or_404(WebsiteMonitor, id=monitor_id)
        get_workspace_for_member(request.user, monitor.workspace_id)
        with transaction.atomic():
            check = WebsiteMonitorRun.objects.create(monitor=monitor)
            from worker.tasks import execute_website_monitor

            transaction.on_commit(lambda: execute_website_monitor.delay(str(check.id)))
        return Response(
            WebsiteMonitorRunSerializer(check).data,
            status=status.HTTP_202_ACCEPTED,
        )


class WebsiteMonitorHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, monitor_id: str) -> Response:
        monitor = get_object_or_404(WebsiteMonitor, id=monitor_id)
        get_workspace_for_member(request.user, monitor.workspace_id)
        return Response(
            WebsiteMonitorRunSerializer(
                monitor.runs.select_related("snapshot")[:100], many=True
            ).data
        )


class ResearchDomainPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        policy, _ = ResearchDomainPolicy.objects.get_or_create(workspace=workspace)
        return Response(ResearchDomainPolicySerializer(policy).data)

    def put(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_workspace_admin(request.user, workspace)
        policy, _ = ResearchDomainPolicy.objects.get_or_create(workspace=workspace)
        serializer = ResearchDomainPolicySerializer(policy, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
