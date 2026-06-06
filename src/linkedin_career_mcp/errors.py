class LinkedInCareerMcpError(Exception):
    """Base exception for expected server errors."""


class ProviderError(LinkedInCareerMcpError):
    """Raised when an upstream provider cannot return usable data."""


class JobNotFoundError(ProviderError):
    """Raised when a requested job detail page is unavailable."""
