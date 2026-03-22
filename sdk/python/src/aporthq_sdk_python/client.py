"""
Production-grade thin Python SDK Client - API calls only.
Aligns with POST /api/verify/policy/{pack_id}: context (required), passport (optional), policy (optional; required when pack_id is IN_BODY).
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union

import aiohttp
from aiohttp import ClientTimeout, ClientError

from .decision_types import (
    PolicyPack,
    PolicyVerificationRequestBody,
    PolicyVerificationRequest,
    PolicyVerificationResponse,
    Jwks,
    JwksKey,
)
from .errors import AportError

# Default headers for all requests (sent on every request; merged with _get_headers())
DEFAULT_HEADERS: Dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "aport-sdk-python/0.1.0",
}
# Optional headers added by _get_headers(): Authorization (Bearer <api_key>), Idempotency-Key


class APortClientOptions:
    """Configuration options for APortClient."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_ms: int = 800,
    ):
        self.base_url = base_url or "https://api.aport.io"
        self.api_key = api_key
        self.timeout_ms = timeout_ms


class APortClient:
    """Production-grade thin SDK Client for APort API."""
    
    def __init__(self, options: APortClientOptions):
        self.opts = options
        self.jwks_cache: Optional[Jwks] = None
        self.jwks_cache_expiry: Optional[float] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        """Ensure HTTP session is created with default headers."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.opts.timeout_ms / 1000)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=DEFAULT_HEADERS,
            )

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_headers(self, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        """Request headers to merge with session defaults: Authorization, Idempotency-Key."""
        headers: Dict[str, str] = {}
        if self.opts.api_key:
            headers["Authorization"] = f"Bearer {self.opts.api_key}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _normalize_url(self, path: str) -> str:
        """Normalize URL by removing trailing slashes and ensuring proper path."""
        base_url = self.opts.base_url.rstrip("/")
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{base_url}{clean_path}"

    async def _make_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with proper error handling."""
        await self._ensure_session()
        
        url = self._normalize_url(path)
        headers = self._get_headers(idempotency_key)
        
        try:
            async with self._session.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
            ) as response:
                server_timing = response.headers.get("server-timing")
                text = await response.text()
                
                try:
                    json_data = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    json_data = {}
                
                if not response.ok:
                    raise AportError(
                        status=response.status,
                        reasons=json_data.get("reasons"),
                        decision_id=json_data.get("decision_id"),
                        server_timing=server_timing,
                        raw_response=text,
                    )
                
                if server_timing:
                    json_data["_meta"] = {"serverTiming": server_timing}
                return json_data
                
        except ClientError as e:
            raise AportError(
                status=0,
                reasons=[{"code": "NETWORK_ERROR", "message": str(e)}],
            )
        except asyncio.TimeoutError:
            raise AportError(
                status=408,
                reasons=[{"code": "TIMEOUT", "message": "Request timeout"}],
            )

    def _build_policy_request_body(
        self,
        *,
        agent_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        passport: Optional[Dict[str, Any]] = None,
        policy: Optional[PolicyPack] = None,
    ) -> Dict[str, Any]:
        """Build request body for POST /api/verify/policy/{pack_id}. API expects context, optional passport, optional policy."""
        ctx = dict(context or {})
        if agent_id is not None:
            ctx["agent_id"] = agent_id
        if policy_id is not None:
            ctx["policy_id"] = policy_id
        if idempotency_key is not None:
            ctx["idempotency_key"] = idempotency_key
        body: Dict[str, Any] = {"context": ctx}
        if passport is not None:
            body["passport"] = passport
        if policy is not None:
            body["policy"] = policy
        return body

    async def verify_policy(
        self,
        agent_id: str,
        policy_id: str,
        context: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        *,
        passport: Optional[Dict[str, Any]] = None,
        policy: Optional[PolicyPack] = None,
    ) -> PolicyVerificationResponse:
        """Verify a policy against an agent (cloud mode). Optionally pass passport and/or policy in body."""
        body = self._build_policy_request_body(
            agent_id=agent_id,
            policy_id=policy_id,
            idempotency_key=idempotency_key,
            context=context,
            passport=passport,
            policy=policy,
        )
        path = "/api/verify/policy/IN_BODY" if policy is not None else f"/api/verify/policy/{policy_id}"
        response_data = await self._make_request(
            "POST",
            path,
            data=body,
            idempotency_key=idempotency_key,
        )
        return PolicyVerificationResponse.from_api_response(response_data)

    async def verify_policy_with_passport(
        self,
        passport: Dict[str, Any],
        policy_id: str,
        context: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify a policy using passport in body (local mode; no registry fetch)."""
        agent_id = passport.get("agent_id")
        body = self._build_policy_request_body(
            agent_id=agent_id,
            policy_id=policy_id,
            idempotency_key=idempotency_key,
            context=context or {},
            passport=passport,
        )
        response_data = await self._make_request(
            "POST",
            f"/api/verify/policy/{policy_id}",
            data=body,
            idempotency_key=idempotency_key,
        )
        return PolicyVerificationResponse.from_api_response(response_data)

    async def verify_policy_with_policy_in_body(
        self,
        agent_id_or_passport: Union[str, Dict[str, Any]],
        policy: PolicyPack,
        context: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify using policy pack in body (pack_id = IN_BODY). Pass agent_id (cloud) or passport dict (local)."""
        if isinstance(agent_id_or_passport, dict):
            passport: Optional[Dict[str, Any]] = agent_id_or_passport
            agent_id = passport.get("agent_id")
        else:
            passport = None
            agent_id = agent_id_or_passport
        body = self._build_policy_request_body(
            agent_id=agent_id,
            policy_id=policy.get("id") if isinstance(policy, dict) else getattr(policy, "id", None),
            idempotency_key=idempotency_key,
            context=context or {},
            passport=passport,
            policy=policy,
        )
        response_data = await self._make_request(
            "POST",
            "/api/verify/policy/IN_BODY",
            data=body,
            idempotency_key=idempotency_key,
        )
        return PolicyVerificationResponse.from_api_response(response_data)

    async def get_decision_token(
        self,
        agent_id: str,
        policy_id: str,
        context: Dict[str, Any] = None,
    ) -> str:
        """Get a decision token for near-zero latency validation."""
        if context is None:
            context = {}
            
        request = PolicyVerificationRequest(
            agent_id=agent_id,
            context=context,
        )
        
        response_data = await self._make_request(
            "POST",
            f"/api/verify/token/{policy_id}",
            data=request.__dict__,
        )
        
        return response_data["token"]

    async def validate_decision_token_local(
        self, token: str
    ) -> PolicyVerificationResponse:
        """Validate a decision token locally using JWKS."""
        try:
            jwks = await self.get_jwks()
            # For now, we'll still use the server endpoint
            # TODO: Implement local JWT validation with JWKS
            return await self.validate_decision_token(token)
        except Exception:
            raise AportError(
                401,
                [{"code": "INVALID_TOKEN", "message": "Token validation failed"}],
            )

    async def validate_decision_token(
        self, token: str
    ) -> PolicyVerificationResponse:
        """Validate a decision token via server (for debugging)."""
        response_data = await self._make_request(
            "POST",
            "/api/verify/token/validate",
            data={"token": token},
        )
        return PolicyVerificationResponse.from_api_response(response_data)

    async def get_passport_view(self, agent_id: str) -> Dict[str, Any]:
        """Get passport verification view (for debugging/about pages)."""
        return await self._make_request("GET", f"/api/passports/{agent_id}/verify_view")

    async def get_jwks(self) -> Jwks:
        """Get JWKS for local token validation."""
        # Check cache first
        if (
            self.jwks_cache
            and self.jwks_cache_expiry
            and time.time() < self.jwks_cache_expiry
        ):
            return self.jwks_cache

        try:
            response_data = await self._make_request("GET", "/jwks.json")
            self.jwks_cache = Jwks(**response_data)
            self.jwks_cache_expiry = time.time() + (5 * 60)  # Cache for 5 minutes
            return self.jwks_cache
        except Exception:
            raise AportError(
                500,
                [{"code": "JWKS_FETCH_FAILED", "message": "Failed to fetch JWKS"}],
            )


class PolicyVerifier:
    """Convenience class for policy-specific verification methods."""
    
    def __init__(self, client: APortClient):
        self.client = client

    async def verify_refund(
        self,
        agent_id: str,
        context: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify the finance.payment.refund.v1 policy."""
        return await self.client.verify_policy(
            agent_id, "finance.payment.refund.v1", context, idempotency_key
        )

    async def verify_release(
        self,
        agent_id: str,
        context: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify the code.release.publish.v1 policy."""
        return await self.client.verify_policy(
            agent_id, "code.release.publish.v1", context, idempotency_key
        )

    async def verify_data_export(
        self,
        agent_id: str,
        context: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify the data.export.create.v1 policy."""
        return await self.client.verify_policy(
            agent_id, "data.export.create.v1", context, idempotency_key
        )

    async def verify_messaging(
        self,
        agent_id: str,
        context: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify the messaging.message.send.v1 policy."""
        return await self.client.verify_policy(
            agent_id, "messaging.message.send.v1", context, idempotency_key
        )

    async def verify_repository(
        self,
        agent_id: str,
        context: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify the code.repository.merge.v1 policy."""
        return await self.client.verify_policy(
            agent_id, "code.repository.merge.v1", context, idempotency_key
        )

    async def verify_deliverable_task_complete(
        self,
        agent_id: str,
        context: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> PolicyVerificationResponse:
        """Verify the deliverable.task.complete.v1 policy (task completion gate)."""
        return await self.client.verify_policy(
            agent_id, "deliverable.task.complete.v1", context, idempotency_key
        )
