"""FastAPI middleware for Agent Passport verification using the thin client SDK.

Supports all API combinations: agent_id (cloud), passport in body (local),
policy in body (pack_id IN_BODY). Delegates to aporthq_sdk_python.
"""

import json
import os
from typing import Callable, Optional, List, Dict, Any, Union
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aporthq_sdk_python import (
    APortClient,
    APortClientOptions,
    PolicyVerifier,
    AportError,
    PolicyVerificationResponse,
)


class AgentRequest(Request):
    """Extended FastAPI Request type to include agent and policy data."""
    agent: Optional[Dict[str, Any]] = None
    policy_result: Optional[Dict[str, Any]] = None


class AgentPassportMiddlewareOptions:
    """Configuration options for the Agent Passport middleware."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_ms: int = 5000,
        fail_closed: bool = True,
        skip_paths: Optional[List[str]] = None,
        policy_id: Optional[str] = None,
        passport_from_body: bool = True,
        policy_from_body: bool = True,
    ):
        self.base_url = base_url or os.getenv("AGENT_PASSPORT_BASE_URL", "https://api.aport.io")
        self.api_key = api_key or os.getenv("AGENT_PASSPORT_API_KEY")
        self.timeout_ms = timeout_ms
        self.fail_closed = fail_closed
        self.skip_paths = skip_paths or ["/health", "/metrics", "/status"]
        self.policy_id = policy_id
        self.passport_from_body = passport_from_body
        self.policy_from_body = policy_from_body


class PolicyMiddlewareOptions:
    """Options for policy-specific middleware."""
    
    def __init__(
        self,
        policy_id: str,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.policy_id = policy_id
        self.agent_id = agent_id
        self.context = context or {}


# Default middleware options
DEFAULT_OPTIONS = AgentPassportMiddlewareOptions()


def create_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> APortClient:
    """Create APortClient with sensible defaults."""
    options = APortClientOptions(
        base_url=base_url or os.getenv("AGENT_PASSPORT_BASE_URL", "https://api.aport.io"),
        api_key=api_key or os.getenv("AGENT_PASSPORT_API_KEY"),
        timeout_ms=timeout_ms or 5000,
    )
    return APortClient(options)


def extract_agent_id(
    request: Request,
    provided_agent_id: Optional[str] = None,
    body_json: Optional[Dict[str, Any]] = None,
    passport_from_body: bool = True,
) -> Optional[str]:
    """Extract agent ID from parameter, headers, or body.passport.agent_id."""
    if provided_agent_id:
        return provided_agent_id
    if passport_from_body and body_json and isinstance(body_json.get("passport"), dict):
        aid = body_json["passport"].get("agent_id")
        if aid:
            return aid
    return (
        request.headers.get("x-agent-passport-id")
        or request.headers.get("x-agent-id")
        or None
    )


async def _read_and_replay_body(request: Request) -> Dict[str, Any]:
    """Read request body, parse JSON, and replace scope['receive'] so the route can read it again."""
    body_bytes = await request.body()
    try:
        body_json = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        body_json = {}
    # Replay body for the route handler
    async def _replay_receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}
    request.scope["receive"] = _replay_receive
    return body_json


def _decision_allow(decision: Union[PolicyVerificationResponse, Dict[str, Any]]) -> bool:
    """Get .allow from SDK response (dataclass or dict)."""
    if hasattr(decision, "allow"):
        return bool(decision.allow)
    return bool(decision.get("allow", False))


def _decision_meta(
    decision: Union[PolicyVerificationResponse, Dict[str, Any]],
) -> Dict[str, Any]:
    """Get decision_id and reasons from SDK response."""
    if hasattr(decision, "decision_id"):
        return {
            "decision_id": getattr(decision, "decision_id", None),
            "reasons": getattr(decision, "reasons", None) or [],
        }
    return {
        "decision_id": decision.get("decision_id"),
        "reasons": decision.get("reasons", []),
    }


def should_skip_request(request: Request, skip_paths: List[str]) -> bool:
    """Check if request should be skipped based on path."""
    return any(request.url.path.startswith(path) for path in skip_paths)


def create_error_response(
    status_code: int,
    error: str,
    message: str,
    additional: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Create error response."""
    response_data = {
        "error": error,
        "message": message,
    }
    if additional:
        response_data.update(additional)
    
    return JSONResponse(
        status_code=status_code,
        content=response_data,
    )


class AgentPassportMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for Agent Passport verification using the thin client SDK."""
    
    def __init__(
        self,
        app: ASGIApp,
        options: Optional[AgentPassportMiddlewareOptions] = None,
        **kwargs
    ):
        """
        Initialize the middleware.
        
        Args:
            app: FastAPI application
            options: Middleware configuration options
            **kwargs: Additional options passed from FastAPI add_middleware
        """
        super().__init__(app)
        
        # Handle options passed directly as kwargs (from FastAPI add_middleware)
        if options is None:
            options = AgentPassportMiddlewareOptions()
        
        # Override with any kwargs passed from FastAPI
        for key, value in kwargs.items():
            if hasattr(options, key):
                setattr(options, key, value)
        
        self.options = options
        self.client = create_client(
            base_url=self.options.base_url,
            api_key=self.options.api_key,
            timeout_ms=self.options.timeout_ms,
        )
        self.verifier = PolicyVerifier(self.client)

    async def dispatch(self, request: Request, call_next):
        """Process the request; support agent_id, passport in body, policy in body."""
        try:
            if should_skip_request(request, self.options.skip_paths):
                return await call_next(request)

            body_json: Dict[str, Any] = {}
            if request.method == "POST" and (self.options.policy_id or self.options.passport_from_body or self.options.policy_from_body):
                body_json = await _read_and_replay_body(request)

            use_passport_from_body = self.options.passport_from_body
            use_policy_from_body = self.options.policy_from_body
            body_passport = body_json.get("passport") if use_passport_from_body and isinstance(body_json.get("passport"), dict) else None
            body_policy = body_json.get("policy") if use_policy_from_body and isinstance(body_json.get("policy"), dict) else None

            agent_id = extract_agent_id(
                request,
                body_json=body_json,
                passport_from_body=use_passport_from_body,
            )
            if not agent_id and not body_passport:
                if self.options.fail_closed:
                    return create_error_response(
                        401,
                        "missing_agent_id",
                        "Agent ID is required. Provide X-Agent-Passport-Id header or body.passport.",
                    )
                return await call_next(request)

            effective_agent_id = agent_id or (body_passport.get("agent_id") if body_passport else None)

            if not self.options.policy_id and not body_policy:
                if body_passport:
                    request.state.agent = {"agent_id": body_passport.get("agent_id"), **body_passport}
                    return await call_next(request)
                try:
                    passport_view = await self.client.get_passport_view(effective_agent_id)
                    request.state.agent = {"agent_id": effective_agent_id, **passport_view}
                    return await call_next(request)
                except AportError as error:
                    return create_error_response(
                        error.status,
                        "agent_verification_failed",
                        error.message,
                        {"agent_id": effective_agent_id},
                    )

            context = {k: v for k, v in body_json.items() if k not in ("passport", "policy")}

            if body_policy:
                agent_id_or_passport: Union[str, Dict[str, Any]] = body_passport if body_passport else effective_agent_id
                decision = await self.client.verify_policy_with_policy_in_body(
                    agent_id_or_passport,
                    body_policy,
                    context,
                )
            elif body_passport:
                decision = await self.client.verify_policy_with_passport(
                    body_passport,
                    self.options.policy_id,
                    context,
                )
            else:
                decision = await self.client.verify_policy(
                    effective_agent_id,
                    self.options.policy_id,
                    context,
                )

            if not _decision_allow(decision):
                meta = _decision_meta(decision)
                return create_error_response(
                    403,
                    "policy_violation",
                    "Policy violation",
                    {
                        "agent_id": effective_agent_id,
                        "policy_id": self.options.policy_id or (body_policy.get("id") if body_policy else None),
                        **meta,
                    },
                )

            request.state.agent = {"agent_id": effective_agent_id}
            request.state.policy_result = decision if isinstance(decision, dict) else {
                "decision_id": getattr(decision, "decision_id", None),
                "allow": getattr(decision, "allow", False),
                "reasons": getattr(decision, "reasons", None) or [],
            }
            return await call_next(request)

        except AportError as error:
            return create_error_response(
                error.status,
                "api_error",
                error.message,
                {"reasons": getattr(error, "reasons", [])},
            )
        except Exception as error:
            print(f"Agent Passport middleware error: {error}")
            return create_error_response(500, "internal_error", "Internal server error")


def agent_passport_middleware(
    options: Optional[AgentPassportMiddlewareOptions] = None
) -> Callable:
    """
    Global middleware that enforces a specific policy on all routes.
    
    Args:
        options: Middleware configuration options
        
    Returns:
        Middleware function
    """
    opts = AgentPassportMiddlewareOptions(**(options.__dict__ if options else {}))
    client = create_client(
        base_url=opts.base_url,
        api_key=opts.api_key,
        timeout_ms=opts.timeout_ms,
    )

    async def middleware(request: Request, call_next):
        try:
            if should_skip_request(request, opts.skip_paths):
                return await call_next(request)

            body_json = {}
            if request.method == "POST" and (opts.policy_id or opts.passport_from_body or opts.policy_from_body):
                body_json = await _read_and_replay_body(request)

            body_passport = body_json.get("passport") if opts.passport_from_body and isinstance(body_json.get("passport"), dict) else None
            body_policy = body_json.get("policy") if opts.policy_from_body and isinstance(body_json.get("policy"), dict) else None

            agent_id = extract_agent_id(request, body_json=body_json, passport_from_body=opts.passport_from_body)
            if not agent_id and not body_passport:
                if opts.fail_closed:
                    return create_error_response(
                        401,
                        "missing_agent_id",
                        "Agent ID is required. Provide X-Agent-Passport-Id header or body.passport.",
                    )
                return await call_next(request)

            effective_agent_id = agent_id or (body_passport.get("agent_id") if body_passport else None)

            if not opts.policy_id and not body_policy:
                if body_passport:
                    request.state.agent = {"agent_id": body_passport.get("agent_id"), **body_passport}
                    return await call_next(request)
                try:
                    passport_view = await client.get_passport_view(effective_agent_id)
                    request.state.agent = {"agent_id": effective_agent_id, **passport_view}
                    return await call_next(request)
                except AportError as error:
                    return create_error_response(
                        error.status,
                        "agent_verification_failed",
                        error.message,
                        {"agent_id": effective_agent_id},
                    )

            context = {k: v for k, v in body_json.items() if k not in ("passport", "policy")}

            if body_policy:
                decision = await client.verify_policy_with_policy_in_body(
                    body_passport or effective_agent_id,
                    body_policy,
                    context,
                )
            elif body_passport:
                decision = await client.verify_policy_with_passport(
                    body_passport,
                    opts.policy_id,
                    context,
                )
            else:
                decision = await client.verify_policy(
                    effective_agent_id,
                    opts.policy_id,
                    context,
                )

            if not _decision_allow(decision):
                meta = _decision_meta(decision)
                return create_error_response(
                    403,
                    "policy_violation",
                    "Policy violation",
                    {
                        "agent_id": effective_agent_id,
                        "policy_id": opts.policy_id or (body_policy.get("id") if body_policy else None),
                        **meta,
                    },
                )

            request.state.agent = {"agent_id": effective_agent_id}
            request.state.policy_result = decision if isinstance(decision, dict) else {
                "decision_id": getattr(decision, "decision_id", None),
                "allow": getattr(decision, "allow", False),
                "reasons": getattr(decision, "reasons", None) or [],
            }
            return await call_next(request)

        except AportError as error:
            return create_error_response(
                error.status,
                "api_error",
                error.message,
                {"reasons": getattr(error, "reasons", [])},
            )
        except Exception as error:
            print(f"Policy verification error: {error}")
            return create_error_response(500, "internal_error", "Internal server error")

    return middleware


def require_policy(policy_id: str, agent_id: Optional[str] = None) -> Callable:
    """Route-specific dependency; supports agent_id, body.passport, body.policy."""
    client = create_client()

    async def policy_dependency(request: Request):
        try:
            body_json = {}
            if request.method == "POST":
                body_json = await _read_and_replay_body(request)
            body_passport = body_json.get("passport") if isinstance(body_json.get("passport"), dict) else None
            body_policy = body_json.get("policy") if isinstance(body_json.get("policy"), dict) else None

            extracted_agent_id = extract_agent_id(request, body_json=body_json, passport_from_body=True)
            if not extracted_agent_id and not body_passport:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": "missing_agent_id",
                        "message": "Agent ID is required. Provide X-Agent-Passport-Id header, function parameter, or body.passport.",
                    },
                )
            effective_agent_id = extracted_agent_id or (body_passport.get("agent_id") if body_passport else None)

            context = {k: v for k, v in body_json.items() if k not in ("passport", "policy")}

            if body_policy:
                decision = await client.verify_policy_with_policy_in_body(
                    body_passport or effective_agent_id,
                    body_policy,
                    context,
                )
            elif body_passport:
                decision = await client.verify_policy_with_passport(
                    body_passport,
                    policy_id,
                    context,
                )
            else:
                decision = await client.verify_policy(
                    effective_agent_id,
                    policy_id,
                    context,
                )

            if not _decision_allow(decision):
                meta = _decision_meta(decision)
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "policy_violation",
                        "message": "Policy violation",
                        "agent_id": effective_agent_id,
                        "policy_id": policy_id,
                        **meta,
                    },
                )

            request.state.agent = {"agent_id": effective_agent_id}
            request.state.policy_result = decision if isinstance(decision, dict) else {
                "decision_id": getattr(decision, "decision_id", None),
                "allow": getattr(decision, "allow", False),
                "reasons": getattr(decision, "reasons", None) or [],
            }
            return {
                "agent": request.state.agent,
                "policy_result": request.state.policy_result,
            }

        except HTTPException:
            # Re-raise HTTPException as-is
            raise
        except AportError as error:
            raise HTTPException(
                status_code=error.status,
                detail={
                    "error": "api_error",
                    "message": error.message,
                    "reasons": getattr(error, "reasons", [])
                }
            )
        except Exception as error:
            print(f"Policy verification error: {error}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_error",
                    "message": "Internal server error"
                }
            )

    return policy_dependency


def require_policy_with_context(
    policy_id: str,
    context: Dict[str, Any],
    agent_id: Optional[str] = None,
) -> Callable:
    """Route-specific middleware with custom context; supports body.passport, body.policy."""
    client = create_client()

    async def middleware(request: Request, call_next):
        try:
            body_json = {}
            if request.method == "POST":
                body_json = await _read_and_replay_body(request)
            body_passport = body_json.get("passport") if isinstance(body_json.get("passport"), dict) else None
            body_policy = body_json.get("policy") if isinstance(body_json.get("policy"), dict) else None

            extracted_agent_id = extract_agent_id(request, provided_agent_id=agent_id, body_json=body_json, passport_from_body=True)
            if not extracted_agent_id and not body_passport:
                return create_error_response(
                    401,
                    "missing_agent_id",
                    "Agent ID is required. Provide X-Agent-Passport-Id header, function parameter, or body.passport.",
                )
            effective_agent_id = extracted_agent_id or (body_passport.get("agent_id") if body_passport else None)

            request_context = {k: v for k, v in body_json.items() if k not in ("passport", "policy")}
            merged_context = {**request_context, **context}

            if body_policy:
                decision = await client.verify_policy_with_policy_in_body(
                    body_passport or effective_agent_id,
                    body_policy,
                    merged_context,
                )
            elif body_passport:
                decision = await client.verify_policy_with_passport(
                    body_passport,
                    policy_id,
                    merged_context,
                )
            else:
                decision = await client.verify_policy(
                    effective_agent_id,
                    policy_id,
                    merged_context,
                )

            if not _decision_allow(decision):
                meta = _decision_meta(decision)
                return create_error_response(
                    403,
                    "policy_violation",
                    "Policy violation",
                    {
                        "agent_id": effective_agent_id,
                        "policy_id": policy_id,
                        **meta,
                    },
                )

            request.state.agent = {"agent_id": effective_agent_id}
            request.state.policy_result = decision if isinstance(decision, dict) else {
                "decision_id": getattr(decision, "decision_id", None),
                "allow": getattr(decision, "allow", False),
                "reasons": getattr(decision, "reasons", None) or [],
            }
            return await call_next(request)

        except AportError as error:
            return create_error_response(
                error.status,
                "api_error",
                error.message,
                {"reasons": getattr(error, "reasons", [])},
            )
        except Exception as error:
            print(f"Policy verification error: {error}")
            return create_error_response(500, "internal_error", "Internal server error")

    return middleware


# Convenience functions for specific policies
def require_refund_policy(agent_id: Optional[str] = None) -> Callable:
    """Require refund policy."""
    return require_policy("finance.payment.refund.v1", agent_id)


def require_data_export_policy(agent_id: Optional[str] = None) -> Callable:
    """Require data export policy."""
    return require_policy("data.export.create.v1", agent_id)


def require_messaging_policy(agent_id: Optional[str] = None) -> Callable:
    """Require messaging policy."""
    return require_policy("messaging.message.send.v1", agent_id)


def require_repository_policy(agent_id: Optional[str] = None) -> Callable:
    """Require repository policy."""
    return require_policy("code.repository.merge.v1", agent_id)


def require_deliverable_task_complete_policy(agent_id: Optional[str] = None) -> Callable:
    """Require deliverable task completion policy."""
    return require_policy("deliverable.task.complete.v1", agent_id)


# Direct SDK functions for convenience (async; await required)
async def get_decision_token(
    agent_id: str,
    policy_id: str,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """Get decision token for near-zero latency validation."""
    client = create_client()
    return await client.get_decision_token(agent_id, policy_id, context or {})


async def validate_decision_token(token: str) -> Dict[str, Any]:
    """Validate decision token via server."""
    client = create_client()
    resp = await client.validate_decision_token(token)
    return _response_to_dict(resp)


async def validate_decision_token_local(token: str) -> Dict[str, Any]:
    """Validate decision token locally using JWKS."""
    client = create_client()
    resp = await client.validate_decision_token_local(token)
    return _response_to_dict(resp)


async def get_passport_view(agent_id: str) -> Dict[str, Any]:
    """Get passport view for debugging/about pages."""
    client = create_client()
    return await client.get_passport_view(agent_id)


async def get_jwks() -> Dict[str, Any]:
    """Get JWKS for local token validation."""
    client = create_client()
    jwks = await client.get_jwks()
    return {"keys": jwks.keys} if hasattr(jwks, "keys") else jwks


def _response_to_dict(resp: Union[PolicyVerificationResponse, Dict[str, Any]]) -> Dict[str, Any]:
    """Convert PolicyVerificationResponse to dict for API compatibility."""
    if isinstance(resp, dict):
        return resp
    return {
        "decision_id": getattr(resp, "decision_id", None),
        "allow": getattr(resp, "allow", False),
        "reasons": getattr(resp, "reasons", None) or [],
        "assurance_level": getattr(resp, "assurance_level", None),
        "expires_in": getattr(resp, "expires_in", None),
        "created_at": getattr(resp, "created_at", None),
    }


# Direct policy verification using PolicyVerifier (async; await required)
async def verify_refund(
    agent_id: str,
    context: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify refund policy."""
    client = create_client()
    verifier = PolicyVerifier(client)
    result = await verifier.verify_refund(agent_id, context, idempotency_key)
    return _response_to_dict(result)


async def verify_release(
    agent_id: str,
    context: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify release policy."""
    client = create_client()
    verifier = PolicyVerifier(client)
    result = await verifier.verify_release(agent_id, context, idempotency_key)
    return _response_to_dict(result)


async def verify_data_export(
    agent_id: str,
    context: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify data export policy."""
    client = create_client()
    verifier = PolicyVerifier(client)
    result = await verifier.verify_data_export(agent_id, context, idempotency_key)
    return _response_to_dict(result)


async def verify_messaging(
    agent_id: str,
    context: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify messaging policy."""
    client = create_client()
    verifier = PolicyVerifier(client)
    result = await verifier.verify_messaging(agent_id, context, idempotency_key)
    return _response_to_dict(result)


async def verify_repository(
    agent_id: str,
    context: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify repository policy."""
    client = create_client()
    verifier = PolicyVerifier(client)
    result = await verifier.verify_repository(agent_id, context, idempotency_key)
    return _response_to_dict(result)