# Agent Passport Middleware - Django

Django middleware for The Passport for AI Agents verification and policy
enforcement.

## Installation

```bash
pip install aporthq-middleware-django
```

## Quick Start

Add the middleware and APort settings to `settings.py`:

```python
MIDDLEWARE = [
    "aporthq_middleware_django.AgentPassportMiddleware",
    *MIDDLEWARE,
]

APORT = {
    "API_KEY": "your_api_key_here",
    "BASE_URL": "https://api.aport.io",
    "FAIL_CLOSED": True,
    "SKIP_PATHS": ["/health", "/metrics", "/status"],
    "POLICY_ID": "finance.payment.refund.v1",
}
```

Every protected request must include an agent identifier:

```bash
curl -H "X-Agent-Passport-Id: ap_a2d10232c6534523812423eec8a1425c45678" \
  http://localhost:8000/api/refunds/
```

On success, the middleware attaches APort data to the request:

```python
def process_refund(request):
    agent = request.aport_agent
    policy_result = request.aport_policy_result
    return JsonResponse({"agent_id": agent["agent_id"]})
```

## Route-Specific Policy

Use `require_policy` when only some views need a policy check:

```python
from django.http import JsonResponse
from aporthq_middleware_django import require_policy


@require_policy("finance.payment.refund.v1")
def process_refund(request):
    return JsonResponse({"ok": True, "agent": request.aport_agent})
```

## Configuration

The middleware reads `settings.APORT` first, then `settings.APORT_*`, then
environment variables.

| Option | Default | Description |
| --- | --- | --- |
| `API_KEY` | `AGENT_PASSPORT_API_KEY` or `APORT_API_KEY` | APort API key |
| `BASE_URL` | `https://api.aport.io` | APort API base URL |
| `TIMEOUT_MS` | `5000` | SDK request timeout |
| `FAIL_CLOSED` | `True` | Reject requests without an agent ID |
| `SKIP_PATHS` | `["/health", "/metrics", "/status"]` | Path prefixes to bypass |
| `POLICY_ID` | `None` | Global policy to enforce |
| `PASSPORT_FROM_BODY` | `True` | Allow `body.passport` local mode |
| `POLICY_FROM_BODY` | `True` | Allow `body.policy` IN_BODY mode |

## Agent ID Sources

The middleware resolves the agent ID in this order:

1. Explicit `agent_id` passed to `require_policy`
2. `body.passport.agent_id`
3. `X-Agent-Passport-Id`
4. `X-Agent-Id`

## Error Responses

All failures return JSON:

```json
{"error": "missing_agent_id", "message": "Agent ID is required. Provide X-Agent-Passport-Id header or body.passport."}
```

Common status codes:

- `401`: missing agent ID
- `403`: policy violation
- SDK status code: APort API errors
- `500`: unexpected internal errors

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest tests -q
.venv/bin/python -m build
```

## License

MIT

