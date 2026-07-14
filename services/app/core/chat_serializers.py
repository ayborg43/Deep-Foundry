"""
Serializers for Conversation/Message — AI-owned data (ai.models, per
DATABASE.md §3.3) read directly by Core's chat views. See ai/interface.py's
docstring for why this is a deliberate, narrow exception to "Core never
imports AI internals": listing/reading conversations and messages is plain
workspace-scoped CRUD with no business rule to bypass.
"""

from rest_framework import serializers

from ai.models import Conversation, ConversationParticipant, Message


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
        ]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)


class MessagePatchSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)
