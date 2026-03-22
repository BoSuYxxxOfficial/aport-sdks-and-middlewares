# Agent Passport Middleware - FastAPI

FastAPI middleware for The Passport for AI Agents verification and policy enforcement.

## Installation

```bash
pip install aporthq-middleware-fastapi
```

## Getting Started

**Key Facts:**

- **Agent ID Required**: Every policy check needs an agent ID
- **Two Options**: Pass agent ID as function parameter (preferred) or use `X-Agent-Passport-Id` header
- **Resolution Priority**: Function parameter > Header > Fail with 401
- **API base URL**: Defaults to `https://api.aport.io` (configurable via `base_url` or `AGENT_PASSPORT_BASE_URL`)
- **Policies**: Any registered policy (e.g. `finance.payment.refund.v1`, `system.command.execute.v1`, `deliverable.task.complete.v1`). See [Available Policies](#available-policies) below. Full list: `GET /api/policies`

| **Method** | **Agent ID Source** | **Security** | **Use Case** |
|------------|-------------------|--------------|--------------|
| **Explicit Parameter** | Function argument | ✅ Highest | Production, explicit control |
| **Header Fallback** | `X-Agent-Passport-Id` | ⚠️ Medium | Backward compatibility |
| **Global Middleware** | `X-Agent-Passport-Id` | ⚠️ Medium | All routes, same policy |

## Quick Start

### 1. Global Policy Enforcement

```python
from fastapi import FastAPI, Request
from aporthq_middleware_fastapi import AgentPassportMiddleware, AgentPassportMiddlewareOptions

app = FastAPI()

# Enforce specific policy globally
app.add_middleware(
    AgentPassportMiddleware,
    options=AgentPassportMiddlewareOptions(
        policy_id="finance.payment.refund.v1",
        fail_closed=True,
    ),
)

# All routes now require finance.payment.refund.v1 policy compliance
@app.post("/api/refunds")
async def process_refund(request: Request):
    body = await request.json()
    return {"success": True, "agent_id": request.state.agent.agent_id}
```

### 2. Route-Specific Policy Enforcement

```python
from aporthq_middleware_fastapi import require_policy, require_policy_with_context

AGENT_ID = "ap_a2d10232c6534523812423eec8a1425c45678"  # Your agent ID

# Explicit agent ID (preferred)
@app.post("/api/refunds")
async def process_refund(request: Request):
    # Policy verified with explicit agent ID
    return {"success": True}

# Add the policy middleware
app.middleware("http")(require_policy("finance.payment.refund.v1", AGENT_ID))

# Header fallback
@app.post("/api/export")
async def export_data(request: Request):
    # Policy verified via header
    return {"success": True}

# Add the policy middleware
app.middleware("http")(require_policy("data.export.create.v1"))  # Uses X-Agent-Passport-Id header
```

### 3. Multiple Policies

```python
# Different policies for different routes
app.middleware("http")(require_policy("finance.payment.refund.v1", AGENT_ID))
@app.post("/api/refunds")
async def refunds(request: Request):
    return {"message": "Refund processed"}

app.middleware("http")(require_policy("data.export.create.v1", AGENT_ID))
@app.post("/api/data/export")
async def export(request: Request):
    return {"message": "Export created"}

app.middleware("http")(require_policy("messaging.message.send.v1", AGENT_ID))
@app.post("/api/messages/send")
async def messaging(request: Request):
    return {"message": "Message sent"}
```

## API Reference

### `agent_passport_middleware(options)`

Global middleware that enforces a specific policy on all routes.

**Parameters:**

- `options.policy_id` (str): Policy ID to enforce (e.g., "finance.payment.refund.v1")
- `options.fail_closed` (bool): Fail if agent ID missing (default: True)
- `options.base_url` (str): APort API base URL (default: "https://api.aport.io")
- `options.timeout_ms` (int): Request timeout in milliseconds (default: 5000)
- `options.skip_paths` (list): Path prefixes to skip (default: `["/health", "/metrics", "/status"]`)
- `options.passport_from_body` (bool): Use request body passport when present (default: True)
- `options.policy_from_body` (bool): Use request body policy when present for IN_BODY (default: True)

**Returns:** Middleware instance

### `require_policy(policy_id, agent_id=None)`

Route-specific middleware that enforces a specific policy.

**Parameters:**

- `policy_id` (str): Policy ID to enforce (e.g., "finance.payment.refund.v1")
- `agent_id` (str, optional): Explicit agent ID (preferred over header)

**Returns:** Middleware function

**Agent ID Resolution:**

1. Function parameter (if provided)
2. `X-Agent-Passport-Id` header (fallback)
3. Fail with 401 error (if neither provided)

### `require_policy_with_context(policy_id, context, agent_id=None)`

Route-specific middleware with custom context.

**Parameters:**

- `policy_id` (str): Policy ID to enforce
- `context` (dict): Custom context data
- `agent_id` (str, optional): Explicit agent ID

**Returns:** Middleware function

## Request Object

After successful policy verification, the request object contains:

```python
@app.post("/api/refunds")
async def process_refund(request: Request):
    # request.state.agent - Verified agent passport data
    print(request.state.agent.agent_id)        # "ap_a2d10232c6534523812423eec8a1425c45678"
    print(request.state.agent.assurance_level) # "L2"
    print(request.state.agent.capabilities)    # ["finance.payment.refund"]
    
    # request.state.policy_result - Policy verification result (decision_id, allow, reasons)
    print(request.state.policy_result.decision_id)
    print(request.state.policy_result.allow)
    print(request.state.policy_result.reasons)
```

## Available Policies

### finance.payment.refund.v1

- **Capabilities:** `["finance.payment.refund"]`
- **Assurance:** L2 minimum
- **Fields:** `order_id`, `customer_id`, `amount_minor`, `currency`, `region`, `reason_code`, `idempotency_key`
- **Rules:** Currency support, region validation, reason code validation, idempotency handling

### data.export.create.v1

- **Capabilities:** `["data.export"]`
- **Assurance:** L1 minimum
- **Fields:** `rows`, `format`, `contains_pii`
- **Rules:** Row limits, PII handling

### messaging.message.send.v1

- **Capabilities:** `["messaging.send"]`
- **Assurance:** L1 minimum
- **Fields:** `channel`, `message_count`, `mentions`
- **Rules:** Rate limits, channel restrictions

### code.repository.merge.v1

- **Capabilities:** `["repo.pr.create", "repo.merge"]`
- **Assurance:** L2 minimum
- **Fields:** `repository`, `base_branch`, `pr_size_kb`
- **Rules:** Repository access, branch protection, PR size limits

### deliverable.task.complete.v1

- **Capabilities:** `["deliverable.task.complete"]`
- **Assurance:** L0 minimum
- **Fields:** `task_id`, `output_type`, `criteria_attestations` (required); `summary`, `tests_passing`, `reviewer_agent_id`, `author_agent_id`, `output_content` (optional per limits)
- **Rules:** Acceptance criteria attestations, summary word count, tests passing, different reviewer, blocked pattern scan

### All Registered Policies

| Policy Pack | Capability | Min Assurance |
|-------------|------------|---------------|
| `agent.session.create.v1` | agent.session.create | L0 |
| `agent.tool.register.v1` | agent.tool.register | L0 |
| `code.release.publish.v1` | repo.release | L3 |
| `code.repository.merge.v1` | repo.pr.create, repo.merge | L2 |
| `data.export.create.v1` | data.export | L1 |
| `data.file.read.v1` | data.file.read | L0 |
| `data.file.write.v1` | data.file.write | L0 |
| `data.report.ingest.v1` | data.report.ingest | L2 |
| `deliverable.task.complete.v1` | deliverable.task.complete | L0 |
| `finance.crypto.trade.v1` | finance.crypto.trade | L3 |
| `finance.payment.charge.v1` | payments.charge | L2 |
| `finance.payment.payout.v1` | payments.payout | L3 |
| `finance.payment.refund.v1` | finance.payment.refund | L2 |
| `finance.transaction.execute.v1` | finance.transaction | L3 |
| `governance.data.access.v1` | data.access | L3 |
| `legal.contract.review.v1` | legal.contract.review | L3 |
| `mcp.tool.execute.v1` | mcp.tool.execute | L0 |
| `messaging.message.send.v1` | messaging.send | L0 |
| `system.command.execute.v1` | system.command.execute | L0 |
| `web.browser.v1` | web.browser | L0 |
| `web.fetch.v1` | web.fetch | L0 |

For schema and required context per policy: `GET /api/policies` or `GET /api/policies/{pack_id}`.

## Error Handling

The middleware returns appropriate HTTP status codes:

```python
# 401 - Missing or invalid agent ID
{
    "error": "missing_agent_id",
    "message": "Agent ID is required. Provide it as X-Agent-Passport-Id header."
}

# 403 - Policy violation
{
    "error": "policy_violation",
    "message": "Policy violation",
    "agent_id": "ap_a2d10232c6534523812423eec8a1425c45678",
    "policy_id": "finance.payment.refund.v1"
}

# 400 - Field validation failed
{
    "error": "field_validation_failed",
    "message": "Field validation failed: Required field 'order_id' is missing"
}
```

## Configuration

### Environment Variables

```bash
# APort API base URL (optional)
AGENT_PASSPORT_BASE_URL=https://api.aport.io

# Default agent ID for development (optional)
AGENT_PASSPORT_AGENT_ID=ap_a2d10232c6534523812423eec8a1425c45678
```

### Skip Paths

```python
app.add_middleware(
    AgentPassportMiddleware,
    options=AgentPassportMiddlewareOptions(
        policy_id="finance.payment.refund.v1",
        skip_paths=["/health", "/metrics", "/status"],
    ),
)
```

## Examples

### E-commerce Refund System

```python
from fastapi import FastAPI, Request
from aporthq_middleware_fastapi import require_policy

app = FastAPI()

AGENT_ID = "ap_a2d10232c6534523812423eec8a1425c45678"

# Refund processing with policy enforcement
app.middleware("http")(require_policy("finance.payment.refund.v1", AGENT_ID))

@app.post("/api/refunds")
async def process_refund(request: Request):
    body = await request.json()
    amount = body.get("amount")
    currency = body.get("currency")
    order_id = body.get("order_id")
    
    # Policy already verified - safe to process
    return {
        "success": True,
        "refund_id": f"ref_{int(time.time() * 1000)}",
        "amount": amount,
        "currency": currency,
        "order_id": order_id,
        "agent_id": request.state.agent.agent_id
    }
```

### Data Export System

```python
# Data export with policy enforcement
app.middleware("http")(require_policy("data.export.create.v1", AGENT_ID))

@app.post("/api/data/export")
async def export_data(request: Request):
    body = await request.json()
    rows = body.get("rows")
    format = body.get("format")
    contains_pii = body.get("contains_pii")
    
    # Policy verified - safe to export
    return {
        "success": True,
        "export_id": f"exp_{int(time.time() * 1000)}",
        "rows": rows,
        "format": format,
        "contains_pii": contains_pii,
        "agent_id": request.state.agent.agent_id
    }
```

### Messaging System

```python
# Messaging with policy enforcement
app.middleware("http")(require_policy("messaging.message.send.v1", AGENT_ID))

@app.post("/api/messages/send")
async def send_message(request: Request):
    body = await request.json()
    channel = body.get("channel")
    message_count = body.get("message_count")
    mentions = body.get("mentions")
    
    # Policy verified - safe to send
    return {
        "success": True,
        "message_id": f"msg_{int(time.time() * 1000)}",
        "channel": channel,
        "message_count": message_count,
        "mentions": mentions,
        "agent_id": request.state.agent.agent_id
    }
```

## License

MIT

---

**Last Updated**: 2025-01-16 00:00:00 UTC