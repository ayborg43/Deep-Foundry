"""
Serializers for Conversation/Message — AI-owned data (ai.models, per
DATABASE.md §3.3) read directly by Core's chat views. See ai/interface.py's
docstring for why this is a deliberate, narrow exception to "Core never
imports AI internals": listing/reading conversations and messages is plain
workspace-scoped CRUD with no business rule to bypass.
"""

from rest_framework import serializers

from ai.models import Conversation, ConversationParticipant, Message
from research.models import MessageCitation


class MessageCitationSerializer(serializers.ModelSerializer):
    source_id = serializers.UUIDField(source="evidence.source_id", read_only=True)
    url = serializers.CharField(source="evidence.source.url", read_only=True)
    canonical_url = serializers.CharField(
        source="evidence.source.canonical_url", read_only=True
    )
    title = serializers.CharField(source="evidence.source.title", read_only=True)
    publisher = serializers.CharField(source="evidence.source.publisher", read_only=True)
    published_at = serializers.DateTimeField(
        source="evidence.source.published_at", read_only=True, allow_null=True
    )
    accessed_at = serializers.DateTimeField(
        source="evidence.source.accessed_at", read_only=True
    )
    passage = serializers.CharField(source="evidence.passage", read_only=True)
    locator = serializers.CharField(source="evidence.locator", read_only=True)
    page_number = serializers.IntegerField(
        source="evidence.page_number", read_only=True, allow_null=True
    )
    language = serializers.CharField(source="evidence.source.language", read_only=True)
    country = serializers.CharField(source="evidence.source.country", read_only=True)

    class Meta:
        model = MessageCitation
        fields = [
            "id",
            "ordinal",
            "claim",
            "source_id",
            "url",
            "canonical_url",
            "title",
            "publisher",
            "published_at",
            "accessed_at",
            "passage",
            "locator",
            "page_number",
            "language",
            "country",
        ]


class ConversationSerializer(serializers.ModelSerializer):
    # Not a stored column — Milestone 4's chat UI needs to know which
    # coworker a conversation is with (to load its name/avatar/tools) but
    # that's only recorded via ConversationParticipant (DATABASE.md §3.3's
    # polymorphic participants model), same lookup chat_views._get_conversation_coworker_id
    # does server-side.
    coworker_id = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "workspace_id",
            "project_id",
            "created_by",
            "title",
            "coworker_id",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "coworker_id", "created_at"]

    def get_coworker_id(self, obj: Conversation) -> str | None:
        participant = obj.participants.filter(
            participant_type=ConversationParticipant.ParticipantType.COWORKER
        ).first()
        return str(participant.participant_id) if participant else None


class MessageSerializer(serializers.ModelSerializer):
    citations = MessageCitationSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "conversation_id",
            "sender_type",
            "sender_id",
            "content",
            "tool_calls",
            "tool_call_id",
            "parent_message_id",
            "status",
            "created_at",
            "citations",
        ]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)


class MessagePatchSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)
