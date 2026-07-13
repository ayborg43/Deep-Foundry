class AdapterError(Exception):
    """Base for any failure talking to a deployment mode's backing service."""


class RateLimitedError(AdapterError):
    """The provider rejected the call for rate limiting — the Router's
    fallback chain treats this distinctly from a hard failure."""


class CapabilityError(Exception):
    """The requested model_config can't do what the caller asked (e.g. tools
    against a model with tool_calling=False). Raised before any network call."""
