# Agent Passport Python SDK

A production-grade thin Python SDK for The Passport for AI Agents, providing easy integration with agent authentication and policy verification via API calls. All policy logic, counters, and enforcement happen on the server side.

## Features

- ✅ **Thin Client Architecture** - No policy logic, no Cloudflare imports, no counters
- ✅ **Production Ready** - Timeouts, retries, proper error handling, Server-Timing support
- ✅ **Type Safe** - Full type hints with comprehensive type definitions
- ✅ **Idempotency Support** - Both header and body idempotency key support
- ✅ **Local Token Validation** - JWKS support for local decision token validation
- ✅ **Multiple Environments** - Production, sandbox, and self-hosted enterprise support
- ✅ **Async/Await** - Modern async Python with aiohttp
- ✅ **Context Manager** - Proper resource management with async context managers

## Installation

```bash
pip install aporthq-sdk-python
```

**Requirements:** Python 3.8 or higher

## Quick Start

```python
import asyncio
from aporthq_sdk_python import APortClient, APortClientOptions, PolicyVerifier, AportError

async def main():
    # Initialize client for production
    client = APortClient(APortClientOptions(
        base_url="https://api.aport.io",  # Production API
        api_key="your-api-key",  # Optional
        timeout_ms=800  # Optional: Request timeout (default: 800ms)
    ))

    # Or for sandbox/testing
    sandbox_client = APortClient(APortClientOptions(
        base_url="https://sandbox.aport.io",  # Sandbox API
        api_key="your-sandbox-key"
    ))

    # Or for self-hosted enterprise
    enterprise_client = APortClient(APortClientOptions(
        base_url="https://your-company.aport.io",  # Your self-hosted instance
        api_key="your-enterprise-key"
    ))

    # Generic policy verification - works with any policy
    try:
        decision = await client.verify_policy(
            agent_id="your-agent-id",
            policy_id="finance.payment.refund.v1",  # Any policy from ./policies
            context={
                "amount": 1000,
                "currency": "USD",
                "order_id": "order_123",
                "reason": "defective"
            },
            idempotency_key="unique-key-123"  # Optional
        )

        if decision.allow:
            print("✅ Policy verification passed!")
            print(f"Decision ID: {decision.decision_id}")
            print(f"Assurance Level: {decision.assurance_level}")
        else:
            print("❌ Policy verification failed!")
            for reason in decision.reasons or []:
                print(f"  - [{reason.get('severity', 'info')}] {reason['code']}: {reason['message']}")
    except AportError as error:
        print(f"API Error {error.status}: {error}")
        print(f"Reasons: {error.reasons}")
        print(f"Decision ID: {error.decision_id}")
    except Exception as error:
        print(f"Policy verification failed: {error}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Environments

The SDK supports different environments through the `base_url` parameter:

- **Production**: `https://api.aport.io` - The main APort API
- **Sandbox**: `https://sandbox.aport.io` - Testing environment with mock data
- **Self-hosted**: `https://your-domain.com` - Your own APort instance

You can also host your own APort service for complete control over policy verification and data privacy.

## API Reference

### `APortClient`

The core client for interacting with the APort API endpoints.

#### `__init__(options: APortClientOptions)`
Initializes the APort client.
- `options.base_url` (str): The base URL of your APort API (e.g., `https://api.aport.io`).
- `options.api_key` (str, optional): Your API Key for authenticated requests.
- `options.timeout_ms` (int, optional): Request timeout in milliseconds (default: 800ms).

#### `async verify_policy(agent_id: str, policy_id: str, context: Dict[str, Any] = None, idempotency_key: str = None, *, passport: Dict = None, policy: PolicyPack = None) -> PolicyVerificationResponse`
Verifies a policy against an agent by calling the `/api/verify/policy/:pack_id` endpoint. Optionally pass `passport` and/or `policy` as keyword-only args for local/dynamic mode.
- `agent_id` (str): The ID of the agent.
- `policy_id` (str): The ID of the policy pack (e.g., `finance.payment.refund.v1`, `deliverable.task.complete.v1`, `code.release.publish.v1`).
- `context` (Dict[str, Any], optional): The policy-specific context data.
- `idempotency_key` (str, optional): An optional idempotency key for the request.
- `passport` (dict, optional, keyword-only): Passport object to send in body (local mode).
- `policy` (PolicyPack, optional, keyword-only): Policy pack to send in body (use path IN_BODY).

#### `async verify_policy_with_passport(passport: Dict[str, Any], policy_id: str, context: Dict[str, Any] = None, idempotency_key: str = None) -> PolicyVerificationResponse`
Verifies a policy using a passport in the request body (local mode; no registry fetch).

#### `async verify_policy_with_policy_in_body(agent_id_or_passport: Union[str, Dict[str, Any]], policy: PolicyPack, context: Dict[str, Any] = None, idempotency_key: str = None) -> PolicyVerificationResponse`
Verifies using a policy pack in the request body (pack_id = IN_BODY). Pass either `agent_id` (cloud) or passport dict (local).

#### `async get_decision_token(agent_id: str, policy_id: str, context: Dict[str, Any] = None) -> str`
Retrieves a short-lived decision token for near-zero latency local validation. Calls `/api/verify/token/:pack_id`.

#### `async validate_decision_token(token: str) -> PolicyVerificationResponse`
Validates a decision token via server (for debugging). Calls `/api/verify/token/validate`.

#### `async validate_decision_token_local(token: str) -> PolicyVerificationResponse`
Validates a decision token locally using JWKS (recommended for production). Falls back to server validation if JWKS unavailable.

#### `async get_passport_view(agent_id: str) -> Dict[str, Any]`
Retrieves a small, cacheable view of an agent's passport (limits, assurance, status) for display purposes (e.g., about pages, debugging). Calls `/api/passports/:id/verify_view`.

#### `async get_jwks() -> Jwks`
Retrieves the JSON Web Key Set for local token validation. Cached for 5 minutes.

### `PolicyVerifier`

A convenience class that wraps `APortClient` to provide policy-specific verification methods.

#### `__init__(client: APortClient)`
Initializes the PolicyVerifier with an `APortClient` instance.

#### `async verify_refund(agent_id: str, context: Dict[str, Any], idempotency_key: str = None) -> PolicyVerificationResponse`
Verifies the `finance.payment.refund.v1` policy.

#### `async verify_repository(agent_id: str, context: Dict[str, Any], idempotency_key: str = None) -> PolicyVerificationResponse`
Verifies the `code.repository.merge.v1` policy.

#### `async verify_deliverable_task_complete(agent_id: str, context: Dict[str, Any], idempotency_key: str = None) -> PolicyVerificationResponse`
Verifies the `deliverable.task.complete.v1` policy (task completion gate).

#### Additional Policy Methods
The `PolicyVerifier` also includes convenience methods for other policies:
- `verify_release()` - Verifies the `code.release.publish.v1` policy
- `verify_data_export()` - Verifies the `data.export.create.v1` policy  
- `verify_messaging()` - Verifies the `messaging.message.send.v1` policy

These methods follow the same pattern as `verify_refund()` and `verify_repository()`.

## Error Handling

The SDK raises `AportError` for API request failures with detailed error information.

```python
from aporthq_sdk_python import AportError

try:
    await client.verify_policy("invalid-agent", "finance.payment.refund.v1", {})
except AportError as error:
    print(f"Status: {error.status}")
    print(f"Message: {error}")
    print(f"Reasons: {error.reasons}")
    print(f"Decision ID: {error.decision_id}")
    print(f"Server Timing: {error.server_timing}")
except Exception as error:
    print(f"Unexpected error: {error}")
```

### Error Types

- **`AportError`**: API request failures with status codes, reasons, and decision IDs
- **Timeout Errors**: 408 status with `TIMEOUT` reason code
- **Network Errors**: 0 status with `NETWORK_ERROR` reason code

## Production Features

### Idempotency Support
The SDK supports idempotency keys in both the request body and the `Idempotency-Key` header (header takes precedence).

```python
decision = await client.verify_policy(
    "agent-123",
    "finance.payment.refund.v1",
    {"amount": 100, "currency": "USD"},
    "unique-idempotency-key"  # Sent in both header and body
)
```

### Server-Timing Support
The SDK automatically captures and exposes Server-Timing headers for performance monitoring.

```python
decision = await client.verify_policy("agent-123", "finance.payment.refund.v1", {})
print("Server timing:", decision._meta.get("serverTiming"))
# Example: "cache;dur=5,db;dur=12"
```

### Local Token Validation
For high-performance scenarios, use local token validation with JWKS:

```python
# Get JWKS (cached for 5 minutes)
jwks = await client.get_jwks()

# Validate token locally (no server round-trip)
decision = await client.validate_decision_token_local(token)
```

### Async Context Manager
Use the client as an async context manager for proper resource management:

```python
async with APortClient(options) as client:
    decision = await client.verify_policy("agent-123", "finance.payment.refund.v1", {})
    # Session is automatically closed
```

### Timeout and Retry Configuration
Configure timeouts and retry behavior:

```python
client = APortClient(APortClientOptions(
    base_url="https://api.aport.io",
    api_key="your-key",
    timeout_ms=500  # 500ms timeout
))
```

## Type Hints

The SDK includes full type hints for all classes, methods, and types.

```python
from aporthq_sdk_python import APortClient, APortClientOptions, PolicyVerificationResponse

options: APortClientOptions = APortClientOptions(
    base_url='https://api.aport.io',
    api_key='my-secret-key',
    timeout_ms=800
)

client: APortClient = APortClient(options)

decision: PolicyVerificationResponse = await client.verify_policy(
    "agent_123", 
    "finance.payment.refund.v1", 
    {"amount": 500, "currency": "EUR"}
)
```

## License

MIT