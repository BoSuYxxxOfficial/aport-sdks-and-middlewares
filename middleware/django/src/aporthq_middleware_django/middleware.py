"""Django middleware for Agent Passport verification using the APort SDK."""

import json
import os
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

from asgiref.sync import async_to_sync
from django.conf import settings
from django.http import HttpRequest, JsonResponse

from aporthq_sdk_python import (
    APortClient,
    APortClientOptions,
    AportError,
    PolicyVerificationResponse,
)

from .types import AgentPassportMiddlewareOptions


DEFAULT_SKIP_PATHS = ["/health", "/metrics", "/status"]


def _settings_dict() -> Dict[str, Any]:
    return getattr(settings, "APORT", {}) if settings.configured else {}


def _setting(name: str, default: Any = None) -> Any:
    aport_settings = _settings_dict()
    if name in aport_settings:
        return aport_settings[name]
    return getattr(settings, f"APORT_{name}", default) if settings.configured else default


def _options_from_settings(**overrides: Any) -> AgentPassportMiddlewareOptions:
    values = {
        "base_url": _setting(
            "BASE_URL",
            os.getenv("AGENT_PASSPORT_BASE_URL")
            or os.getenv("APORT_BASE_URL")
            or "https://api.aport.io",
        ),
        "api_key": _setting(
            "API_KEY",
            os.getenv("AGENT_PASSPORT_API_KEY") or os.getenv("APORT_API_KEY"),
        ),
        "timeout_ms": _setting("TIMEOUT_MS", 5000),
        "fail_closed": _setting("FAIL_CLOSED", True),
        "skip_paths": _setting("SKIP_PATHS", DEFAULT_SKIP_PATHS),
        "policy_id": _setting("POLICY_ID", None),
        "passport_from_body": _setting("PASSPORT_FROM_BODY", True),
        "policy_from_body": _setting("POLICY_FROM_BODY", True),
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    return AgentPassportMiddlewareOptions(**values)


def create_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> APortClient:
    """Create an APort client with Django settings and env defaults."""
    options = _options_from_settings(
        base_url=base_url,
        api_key=api_key,
        timeout_ms=timeout_ms,
    )
    return APortClient(
        APortClientOptions(
            base_url=options.base_url,
            api_key=options.api_key,
            timeout_ms=options.timeout_ms,
        )
    )


def _json_error(
    status: int,
    error: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> JsonResponse:
    payload = {"error": error, "message": message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def _decision_allow(decision: Union[PolicyVerificationResponse, Dict[str, Any]]) -> bool:
    if hasattr(decision, "allow"):
        return bool(decision.allow)
    return bool(decision.get("allow", False))


def _decision_meta(
    decision: Union[PolicyVerificationResponse, Dict[str, Any]]
) -> Dict[str, Any]:
    if hasattr(decision, "decision_id"):
        return {
            "decision_id": getattr(decision, "decision_id", None),
            "reasons": getattr(decision, "reasons", None) or [],
        }
    return {
        "decision_id": decision.get("decision_id"),
        "reasons": decision.get("reasons", []),
    }


def _decision_payload(
    decision: Union[PolicyVerificationResponse, Dict[str, Any]]
) -> Dict[str, Any]:
    if isinstance(decision, dict):
        return decision
    return {
        "decision_id": getattr(decision, "decision_id", None),
        "allow": getattr(decision, "allow", False),
        "reasons": getattr(decision, "reasons", None) or [],
    }


def _body_json(request: HttpRequest) -> Dict[str, Any]:
    if request.method not in {"POST", "PUT", "PATCH"}:
        return {}
    content_type = request.META.get("CONTENT_TYPE", "")
    if "application/json" not in content_type:
        return {}
    try:
        return json.loads(request.body.decode(request.encoding or "utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _extract_agent_id(
    request: HttpRequest,
    provided_agent_id: Optional[str] = None,
    body_json: Optional[Dict[str, Any]] = None,
    passport_from_body: bool = True,
) -> Optional[str]:
    if provided_agent_id:
        return provided_agent_id
    if passport_from_body and body_json and isinstance(body_json.get("passport"), dict):
        agent_id = body_json["passport"].get("agent_id")
        if agent_id:
            return agent_id
    return (
        request.headers.get("X-Agent-Passport-Id")
        or request.headers.get("X-Agent-Id")
        or None
    )


def _context_from_body(body_json: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in body_json.items()
        if key not in ("passport", "policy")
    }


def _should_skip(path: str, skip_paths: List[str]) -> bool:
    return any(path.startswith(skip_path) for skip_path in skip_paths)


def _handle_aport_error(error: AportError) -> JsonResponse:
    return _json_error(
        error.status or 500,
        "api_error",
        str(error),
        {
            "decision_id": getattr(error, "decision_id", None),
            "reasons": getattr(error, "reasons", []) or [],
        },
    )


def _verify_request(
    request: HttpRequest,
    *,
    client: APortClient,
    options: AgentPassportMiddlewareOptions,
    policy_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Optional[JsonResponse]:
    body_json = _body_json(request)
    body_passport = (
        body_json.get("passport")
        if options.passport_from_body and isinstance(body_json.get("passport"), dict)
        else None
    )
    body_policy = (
        body_json.get("policy")
        if options.policy_from_body and isinstance(body_json.get("policy"), dict)
        else None
    )
    extracted_agent_id = _extract_agent_id(
        request,
        provided_agent_id=agent_id,
        body_json=body_json,
        passport_from_body=options.passport_from_body,
    )
    if not extracted_agent_id and not body_passport:
        if options.fail_closed:
            return _json_error(
                401,
                "missing_agent_id",
                "Agent ID is required. Provide X-Agent-Passport-Id header or body.passport.",
            )
        return None

    effective_agent_id = extracted_agent_id or body_passport.get("agent_id")
    effective_policy_id = policy_id or options.policy_id
    context = _context_from_body(body_json)

    try:
        if body_policy:
            decision = async_to_sync(client.verify_policy_with_policy_in_body)(
                body_passport or effective_agent_id,
                body_policy,
                context,
            )
        elif body_passport and effective_policy_id:
            decision = async_to_sync(client.verify_policy_with_passport)(
                body_passport,
                effective_policy_id,
                context,
            )
        elif effective_policy_id:
            decision = async_to_sync(client.verify_policy)(
                effective_agent_id,
                effective_policy_id,
                context,
            )
        else:
            if body_passport:
                request.aport_agent = {
                    "agent_id": body_passport.get("agent_id"),
                    **body_passport,
                }
                return None
            passport_view = async_to_sync(client.get_passport_view)(effective_agent_id)
            request.aport_agent = {"agent_id": effective_agent_id, **passport_view}
            return None
    except AportError as error:
        return _handle_aport_error(error)
    except Exception:
        return _json_error(500, "internal_error", "Internal server error")

    if not _decision_allow(decision):
        meta = _decision_meta(decision)
        return _json_error(
            403,
            "policy_violation",
            "Policy violation",
            {
                "agent_id": effective_agent_id,
                "policy_id": effective_policy_id
                or (body_policy.get("id") if body_policy else None),
                **meta,
            },
        )

    request.aport_agent = {"agent_id": effective_agent_id}
    request.aport_policy_result = _decision_payload(decision)
    return None


class AgentPassportMiddleware:
    """Django middleware for Agent Passport verification and policy checks."""

    sync_capable = True
    async_capable = False

    def __init__(self, get_response: Callable, **kwargs: Any):
        self.get_response = get_response
        self.options = _options_from_settings(**kwargs)
        self.client = create_client(
            base_url=self.options.base_url,
            api_key=self.options.api_key,
            timeout_ms=self.options.timeout_ms,
        )

    def __call__(self, request: HttpRequest):
        if _should_skip(request.path, self.options.skip_paths):
            return self.get_response(request)

        response = _verify_request(request, client=self.client, options=self.options)
        if response is not None:
            return response
        return self.get_response(request)


def require_policy(policy_id: str, agent_id: Optional[str] = None) -> Callable:
    """Decorate a Django view so it requires a successful APort policy check."""

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any):
            options = _options_from_settings(policy_id=policy_id)
            client = create_client(
                base_url=options.base_url,
                api_key=options.api_key,
                timeout_ms=options.timeout_ms,
            )
            response = _verify_request(
                request,
                client=client,
                options=options,
                policy_id=policy_id,
                agent_id=agent_id,
            )
            if response is not None:
                return response
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
