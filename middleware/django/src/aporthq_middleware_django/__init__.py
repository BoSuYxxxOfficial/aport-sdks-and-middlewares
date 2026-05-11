"""Django middleware for Agent Passport verification."""

from .middleware import (
    AgentPassportMiddleware,
    AgentPassportMiddlewareOptions,
    create_client,
    require_policy,
)

__version__ = "0.1.4"

__all__ = [
    "AgentPassportMiddleware",
    "AgentPassportMiddlewareOptions",
    "create_client",
    "require_policy",
]
