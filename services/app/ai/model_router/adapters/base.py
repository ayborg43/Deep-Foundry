"""
Deployment-mode adapter contract, per ARCHITECTURE.md §5. Every adapter —
DeepSeek Cloud today, the planned self-hosted DeepSeek adapter later —
implements this identically so the Router (and everything above it) never
special-cases which one is active.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal

from ai.model_router.types import (
    Capabilities,
    ChatMessage,
    GenerateResult,
    ModelConfig,
    ToolDefinition,
    Usage,
)


class ModelAdapter(ABC):
    @abstractmethod
    def generate(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
        model_config: ModelConfig,
    ) -> GenerateResult:
        """Returns a NormalizedResponse, or an Iterator[StreamChunk] when
        model_config.stream is True."""

    @abstractmethod
    def capabilities(self, model_id: str) -> Capabilities: ...

    @abstractmethod
    def estimate_cost(self, usage: Usage, model_id: str) -> Decimal: ...

    @abstractmethod
    def health_check(self) -> bool: ...
