"""Phase 4 adaptive collaboration services.

The critical invariant in this module is that a proposal is only a request:
the requested tool or skill is attached in ``review_capability_proposal``
after an authorized human explicitly approves it.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai.memory import write_memory
from ai.models import Conversation, ConversationParticipant, MemoryEntry
from core.interface import write_audit_log
from core.models import (
    AgentTeam,
    CapabilityProposal,
    ConsensusSession,
    ConsensusVote,
    Coworker,
    CoworkerSkillAttachment,
    CoworkerToolAttachment,
    MarketplaceInstall,
    MemoryConflict,
    SkillVersion,
    Task,
    Tool,
    User,
    VoiceSession,
    Workspace,
    WorkspaceMember,
)


def _require_admin(user: User, workspace: Workspace) -> WorkspaceMember:
    member = WorkspaceMember.objects.filter(workspace=workspace, user=user).first()
    if member is None or member.role not in (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN):
        raise PermissionDenied("Only a workspace Owner/Admin can perform this action.")
    return member


def create_capability_proposal(
    *, coworker: Coworker, target_type: str, target_id, rationale: str,
    proposed_by_type: str = CapabilityProposal.ProposedByType.COWORKER,
) -> CapabilityProposal:
    rationale = rationale.strip()
    if not rationale:
        raise ValidationError({"rationale": "Explain why this capability is needed."})
    if proposed_by_type not in CapabilityProposal.ProposedByType.values:
        raise ValidationError({"proposed_by_type": "Use coworker or user."})
    if target_type == CapabilityProposal.TargetType.TOOL:
        target = Tool.objects.filter(id=target_id).first()
        if target is None:
            raise ValidationError({"target_id": "Tool not found."})
        target_name = target.name
    elif target_type == CapabilityProposal.TargetType.SKILL:
        target = SkillVersion.objects.select_related("listing_version__listing").filter(
            id=target_id,
            listing_version__installs__workspace=coworker.workspace,
        ).first()
        if target is None:
            raise ValidationError({"target_id": "Install this skill in the workspace before proposing it."})
        target_name = target.listing_version.listing.name
    else:
        raise ValidationError({"target_type": "Use tool or skill."})
    if CapabilityProposal.objects.filter(
        coworker=coworker, target_type=target_type, target_id=target.id, status="pending"
    ).exists():
        raise ValidationError("An open proposal already exists for this capability.")
    proposal = CapabilityProposal.objects.create(
        workspace=coworker.workspace,
        coworker=coworker,
        proposed_by_type=proposed_by_type,
        target_type=target_type,
        target_id=target.id,
        target_name=target_name,
        rationale=rationale,
    )
    write_audit_log(
        actor_type="coworker" if proposed_by_type == "coworker" else "user",
        actor_id=coworker.id,
        action="capability.proposed",
        resource_type="capability_proposal",
        resource_id=proposal.id,
        workspace_id=coworker.workspace_id,
        metadata={"target_type": target_type, "target_name": target_name},
    )
    return proposal


@transaction.atomic
def review_capability_proposal(
    proposal: CapabilityProposal, *, user: User, approve: bool
) -> CapabilityProposal:
    proposal = CapabilityProposal.objects.select_for_update().select_related(
        "workspace", "coworker"
    ).get(id=proposal.id)
    _require_admin(user, proposal.workspace)
    if proposal.status != CapabilityProposal.Status.PENDING:
        raise ValidationError("This capability proposal has already been reviewed.")
    if approve:
        if proposal.target_type == CapabilityProposal.TargetType.TOOL:
            tool = Tool.objects.filter(id=proposal.target_id).first()
            if tool is None:
                raise ValidationError("The proposed tool no longer exists.")
            CoworkerToolAttachment.objects.update_or_create(
                coworker=proposal.coworker, tool=tool, defaults={"enabled": True}
            )
        else:
            skill = SkillVersion.objects.filter(
                id=proposal.target_id,
                listing_version__installs__workspace=proposal.workspace,
            ).first()
            if skill is None:
                raise ValidationError("The proposed skill is not installed in this workspace.")
            CoworkerSkillAttachment.objects.update_or_create(
                coworker=proposal.coworker, skill=skill, defaults={"enabled": True}
            )
    proposal.status = (
        CapabilityProposal.Status.APPROVED if approve else CapabilityProposal.Status.DENIED
    )
    proposal.reviewed_by = user
    proposal.reviewed_at = timezone.now()
    proposal.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    write_audit_log(
        actor_type="user", actor_id=user.id,
        action=f"capability.{proposal.status}", resource_type="capability_proposal",
        resource_id=proposal.id, workspace_id=proposal.workspace_id,
        metadata={"target_type": proposal.target_type, "target_name": proposal.target_name},
    )
    return proposal


def _memory_subject(content: str) -> str | None:
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    if ":" not in first_line:
        return None
    subject = re.sub(r"\s+", " ", first_line.split(":", 1)[0]).strip().lower()
    return subject[:255] if 2 <= len(subject) <= 255 else None


def detect_memory_conflicts(workspace: Workspace) -> list[MemoryConflict]:
    """Detect explicit ``subject: value`` disagreements across coworker scopes.

    This deliberately avoids guessing at semantic contradictions. The format is
    explainable, deterministic, and users can also report arbitrary pairs via API.
    """
    grouped: dict[str, list[MemoryEntry]] = defaultdict(list)
    rows = MemoryEntry.objects.filter(
        workspace=workspace, scope=MemoryEntry.Scope.COWORKER, is_long_term=True
    ).order_by("created_at")
    for memory in rows:
        subject = _memory_subject(memory.content)
        if subject:
            grouped[subject].append(memory)
    created: list[MemoryConflict] = []
    for subject, memories in grouped.items():
        for index, left in enumerate(memories):
            for right in memories[index + 1:]:
                if left.scope_id == right.scope_id or left.content.strip() == right.content.strip():
                    continue
                left_id, right_id = sorted((left.id, right.id), key=str)
                conflict, was_created = MemoryConflict.objects.get_or_create(
                    workspace=workspace,
                    left_memory_id=left_id,
                    right_memory_id=right_id,
                    defaults={
                        "subject": subject,
                        "left_content": left.content if left.id == left_id else right.content,
                        "right_content": right.content if right.id == right_id else left.content,
                    },
                )
                if was_created:
                    created.append(conflict)
    return created


def report_memory_conflict(
    workspace: Workspace, *, left_memory_id, right_memory_id, subject: str
) -> MemoryConflict:
    if str(left_memory_id) == str(right_memory_id):
        raise ValidationError("Choose two different memories.")
    memories = {
        str(row.id): row for row in MemoryEntry.objects.filter(
            workspace=workspace, id__in=[left_memory_id, right_memory_id]
        )
    }
    if len(memories) != 2:
        raise ValidationError("Both memories must belong to this workspace.")
    left_id, right_id = sorted((left_memory_id, right_memory_id), key=str)
    left, right = memories[str(left_id)], memories[str(right_id)]
    conflict, _ = MemoryConflict.objects.get_or_create(
        workspace=workspace, left_memory_id=left_id, right_memory_id=right_id,
        defaults={
            "subject": subject.strip()[:255] or "Reported conflict",
            "left_content": left.content, "right_content": right.content,
        },
    )
    return conflict


@transaction.atomic
def resolve_memory_conflict(
    conflict: MemoryConflict, *, user: User, strategy: str, merged_content: str = ""
) -> MemoryConflict:
    conflict = MemoryConflict.objects.select_for_update().select_related("workspace").get(id=conflict.id)
    _require_admin(user, conflict.workspace)
    if conflict.status == MemoryConflict.Status.RESOLVED:
        raise ValidationError("This memory conflict is already resolved.")
    if strategy == MemoryConflict.ResolutionStrategy.KEEP_LEFT:
        resolved = conflict.left_content
    elif strategy == MemoryConflict.ResolutionStrategy.KEEP_RIGHT:
        resolved = conflict.right_content
    elif strategy == MemoryConflict.ResolutionStrategy.MERGE:
        resolved = merged_content.strip()
        if not resolved:
            raise ValidationError({"merged_content": "Merged content is required."})
    else:
        raise ValidationError({"strategy": "Use keep_left, keep_right, or merge."})
    source_rows = list(MemoryEntry.objects.filter(
        workspace=conflict.workspace, id__in=[conflict.left_memory_id, conflict.right_memory_id]
    ))
    for scope_id in {row.scope_id for row in source_rows}:
        write_memory(
            workspace_id=conflict.workspace_id,
            scope=MemoryEntry.Scope.COWORKER,
            scope_id=scope_id,
            content=f"Resolved {conflict.subject}: {resolved}",
            source_ref_id=conflict.id,
        )
    conflict.status = MemoryConflict.Status.RESOLVED
    conflict.resolution_strategy = strategy
    conflict.resolved_content = resolved
    conflict.resolved_by = user
    conflict.resolved_at = timezone.now()
    conflict.save(update_fields=[
        "status", "resolution_strategy", "resolved_content", "resolved_by", "resolved_at"
    ])
    write_audit_log(
        actor_type="user", actor_id=user.id, action="memory_conflict.resolved",
        resource_type="memory_conflict", resource_id=conflict.id,
        workspace_id=conflict.workspace_id, metadata={"strategy": strategy},
    )
    return conflict


def start_consensus_session(
    team: AgentTeam, *, user: User, question: str, options: list[str], method: str
) -> ConsensusSession:
    workspace = team.workspace
    if not WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
        raise PermissionDenied("You are not a member of this team workspace.")
    question = question.strip()
    if not question:
        raise ValidationError({"question": "A decision question is required."})
    clean_options = list(dict.fromkeys(str(option).strip() for option in options if str(option).strip()))
    if len(clean_options) < 2 or len(clean_options) > 10:
        raise ValidationError({"options": "Provide between 2 and 10 distinct options."})
    if method not in ConsensusSession.Method.values:
        raise ValidationError({"method": "Invalid consensus method."})
    members = list(team.current_version.members.select_related("coworker")) if team.current_version else []
    if len(members) < 2:
        raise ValidationError("Consensus requires at least two team members.")
    with transaction.atomic():
        session = ConsensusSession.objects.create(
            agent_team=team, question=question, options=clean_options,
            method=method, created_by=user,
        )
        tasks = []
        for member in members:
            tasks.append(Task.objects.create(
                workspace=workspace, coworker=member.coworker,
                created_by_type=Task.CreatedByType.USER, created_by_id=user.id,
                title=f"Consensus vote: {question[:180]}",
                description=(
                    f"Choose exactly one option for: {question}\nOptions: {json.dumps(clean_options)}\n"
                    "Return JSON only: {\"option\": \"exact option\", \"confidence\": 0.0, "
                    "\"rationale\": \"brief reason\"}."
                ),
                execution_state={"consensus_session_id": str(session.id)},
            ))
        from worker.tasks import execute_background_task
        for task in tasks:
            transaction.on_commit(lambda task_id=str(task.id): execute_background_task.delay(task_id))
    return session


def _parse_vote(result: str, options: list[str]) -> tuple[str, Decimal, str] | None:
    raw = result.strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        payload = json.loads(fenced)
    except (json.JSONDecodeError, TypeError):
        payload = {}
    candidate = str(payload.get("option", "")).strip()
    option = next((item for item in options if item.casefold() == candidate.casefold()), None)
    if option is None:
        matches = [item for item in options if item.casefold() in raw.casefold()]
        if len(matches) == 1:
            option = matches[0]
    if option is None:
        return None
    try:
        confidence = Decimal(str(payload.get("confidence", "1")))
    except InvalidOperation:
        confidence = Decimal("1")
    confidence = min(Decimal("1"), max(Decimal("0"), confidence))
    return option, confidence, str(payload.get("rationale", raw))[:4000]


@transaction.atomic
def record_consensus_vote_from_task(task: Task) -> ConsensusVote | None:
    session_id = task.execution_state.get("consensus_session_id")
    if not session_id or task.status != Task.Status.COMPLETED:
        return None
    # Lock only the session row. Joining through AgentTeam.current_version
    # (nullable during version creation) makes PostgreSQL reject FOR UPDATE
    # against the nullable side of that outer join.
    session = ConsensusSession.objects.select_for_update().get(id=session_id)
    parsed = _parse_vote(task.result, session.options)
    if parsed is None:
        finalize_consensus(session)
        return None
    option, confidence, rationale = parsed
    vote, _ = ConsensusVote.objects.update_or_create(
        session=session, coworker=task.coworker,
        defaults={"task": task, "option": option, "confidence": confidence, "rationale": rationale},
    )
    finalize_consensus(session)
    return vote


def finalize_consensus(session: ConsensusSession) -> ConsensusSession:
    expected = session.agent_team.current_version.members.count()
    finished = Task.objects.filter(execution_state__consensus_session_id=str(session.id)).exclude(
        status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS, Task.Status.NEEDS_APPROVAL]
    ).count()
    votes = list(session.votes.all())
    if finished < expected:
        return session
    scores: dict[str, Decimal] = defaultdict(Decimal)
    for vote in votes:
        scores[vote.option] += (
            vote.confidence if session.method == ConsensusSession.Method.CONFIDENCE_WEIGHTED else Decimal("1")
        )
    winner = ""
    if votes and session.method == ConsensusSession.Method.UNANIMOUS:
        winner = votes[0].option if len(votes) == expected and len({v.option for v in votes}) == 1 else ""
    elif scores and len(votes) > expected / 2:
        high = max(scores.values())
        winners = [option for option, score in scores.items() if score == high]
        winner = winners[0] if len(winners) == 1 else ""
    session.status = ConsensusSession.Status.DECIDED if winner else ConsensusSession.Status.DEADLOCKED
    session.result_option = winner
    session.completed_at = timezone.now()
    session.save(update_fields=["status", "result_option", "completed_at"])
    return session


def create_voice_session(
    *, workspace: Workspace, coworker: Coworker, user: User, language: str
) -> VoiceSession:
    if coworker.workspace_id != workspace.id:
        raise ValidationError("The coworker does not belong to this workspace.")
    conversation = Conversation.objects.create(
        workspace=workspace, created_by=user, title=f"Voice with {coworker.name}"
    )
    ConversationParticipant.objects.bulk_create([
        ConversationParticipant(
            conversation=conversation,
            participant_type=ConversationParticipant.ParticipantType.USER,
            participant_id=user.id,
        ),
        ConversationParticipant(
            conversation=conversation,
            participant_type=ConversationParticipant.ParticipantType.COWORKER,
            participant_id=coworker.id,
        ),
    ])
    return VoiceSession.objects.create(
        workspace=workspace, coworker=coworker, user=user,
        conversation_id=conversation.id, language=(language or "en-US")[:20],
    )
