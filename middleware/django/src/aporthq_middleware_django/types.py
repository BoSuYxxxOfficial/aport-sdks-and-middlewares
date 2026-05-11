"""Type definitions for the Django middleware."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AgentPassportMiddlewareOptions:
    """Configuration options for Agent Passport Django middleware."""

    base_url: str
    api_key: Optional[str]
    timeout_ms: int
    fail_closed: bool
    skip_paths: List[str]
    policy_id: Optional[str]
    passport_from_body: bool
    policy_from_body: bool


PolicyResult = Dict[str, Any]

