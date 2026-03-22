"""
Agent Passport SDK for Python

A production-grade thin Python SDK for The Passport for AI Agents, providing
easy integration with agent authentication and policy verification via API calls.
All policy logic, counters, and enforcement happen on the server side.
"""

from .client import APortClient, APortClientOptions, PolicyVerifier
from .decision_types import (
    Decision,
    DecisionReason,
    VerificationContext,
    PolicyPack,
    PolicyVerificationRequestBody,
    PolicyVerificationRequest,
    PolicyVerificationResponse,
    Jwks,
)
from .errors import AportError

# Backward compatibility - re-export from shared_types
from .shared_types import PassportData, AgentPassport

__version__ = "0.1.4"
__all__ = [
    # Core SDK
    "APortClient",
    "APortClientOptions",
    "PolicyVerifier",
    "AportError",

    # Decision types
    "Decision",
    "DecisionReason",
    "VerificationContext",
    "PolicyPack",
    "PolicyVerificationRequestBody",
    "PolicyVerificationRequest",
    "PolicyVerificationResponse",
    "Jwks",

    # Backward compatibility
    "PassportData",
    "AgentPassport",
]