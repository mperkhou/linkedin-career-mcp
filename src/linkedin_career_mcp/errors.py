class LinkedInCareerMcpError(Exception):
    """Base exception for expected server errors."""


class ProviderError(LinkedInCareerMcpError):
    """Raised when an upstream provider cannot return usable data."""


class JobNotFoundError(ProviderError):
    """Raised when a requested job detail page is unavailable."""


class WorkflowError(LinkedInCareerMcpError):
    """Raised when a local multi-step workflow cannot complete."""


class OllamaError(WorkflowError):
    """Raised when local Ollama generation fails."""
