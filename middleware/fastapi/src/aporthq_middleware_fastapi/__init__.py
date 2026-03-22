"""FastAPI middleware for Agent Passport verification."""

from .middleware import (
    AgentPassportMiddleware,
    AgentPassportMiddlewareOptions,
    PolicyMiddlewareOptions,
    AgentRequest,
    agent_passport_middleware,
    require_policy,
    require_policy_with_context,
    require_refund_policy,
    require_data_export_policy,
    require_messaging_policy,
    require_repository_policy,
    require_deliverable_task_complete_policy,
    # Direct SDK functions
    get_decision_token,
    validate_decision_token,
    validate_decision_token_local,
    get_passport_view,
    get_jwks,
    verify_refund,
    verify_release,
    verify_data_export,
    verify_messaging,
    verify_repository,
)

# Re-export SDK types for convenience
from aporthq_sdk_python import (
    AportError, 
    PolicyVerificationResponse,
    APortClient,
    APortClientOptions,
    PolicyVerifier,
    Jwks,
    Decision,
    DecisionReason,
    VerificationContext,
    PolicyVerificationRequest,
    PassportData,
    AgentPassport,
)

__all__ = [
    # Middleware classes
    "AgentPassportMiddleware",
    "AgentPassportMiddlewareOptions",
    "PolicyMiddlewareOptions",
    "AgentRequest",
    
    # Middleware functions
    "agent_passport_middleware",
    "require_policy",
    "require_policy_with_context",
    "require_refund_policy",
    "require_data_export_policy",
    "require_messaging_policy",
    "require_repository_policy",
    "require_deliverable_task_complete_policy",
    
    # Direct SDK functions
    "get_decision_token",
    "validate_decision_token",
    "validate_decision_token_local",
    "get_passport_view",
    "get_jwks",
    "verify_refund",
    "verify_release",
    "verify_data_export",
    "verify_messaging",
    "verify_repository",
    
    # SDK types
    "AportError",
    "PolicyVerificationResponse",
    "APortClient",
    "APortClientOptions",
    "PolicyVerifier",
    "Jwks",
    "Decision",
    "DecisionReason",
    "VerificationContext",
    "PolicyVerificationRequest",
    "PassportData",
    "AgentPassport",
]