# Agent Passport SDKs and Middleware

This directory contains SDKs and middleware for integrating with The Passport for AI Agents across different platforms and programming languages.

## 📦 Available Packages

### Node.js SDK
- **Package**: `@aporthq/sdk-node`
- **Location**: `./node/`
- **Description**: Node.js thin client for policy verification and passport views (fetch-based)

### Python SDK
- **Package**: `aporthq-sdk-python`
- **Location**: `./python/`
- **Description**: Python thin client for policy verification and passport views (async aiohttp)

### Express.js Middleware
- **Package**: `@aporthq/middleware-express`
- **Location**: `../middleware/express/`
- **Description**: Express.js middleware for agent verification and policy enforcement

### FastAPI Middleware
- **Package**: `aporthq-middleware-fastapi`
- **Location**: `../middleware/fastapi/`
- **Description**: FastAPI middleware for agent verification and policy enforcement

## 🚀 Quick Start

### Node.js

```bash
npm install @aporthq/sdk-node
```

```javascript
import { APortClient, PolicyVerifier, AportError } from '@aporthq/sdk-node';

const client = new APortClient({
  baseUrl: 'https://api.aport.io',
  apiKey: 'your-api-key',
  timeoutMs: 800,
});

const decision = await client.verifyPolicy(
  'your-agent-id',
  'finance.payment.refund.v1',
  { amount: 1000, currency: 'USD', order_id: 'order_123' }
);
if (decision.allow) console.log('Allowed:', decision.decision_id);
```

### Python

```bash
pip install aporthq-sdk-python
```

```python
import asyncio
from aporthq_sdk_python import APortClient, APortClientOptions, AportError

async def main():
    client = APortClient(APortClientOptions(
        base_url="https://api.aport.io",
        api_key="your-api-key",
        timeout_ms=800,
    ))
    decision = await client.verify_policy(
        "your-agent-id",
        "finance.payment.refund.v1",
        {"amount": 1000, "currency": "USD", "order_id": "order_123"},
    )
    if decision.allow:
        print("Allowed:", decision.decision_id)

asyncio.run(main())
```

### Express.js Middleware

```bash
npm install @aporthq/middleware-express
```

```javascript
const express = require('express');
const { agentPassportMiddleware, requirePolicy } = require('@aporthq/middleware-express');

const app = express();
app.use(express.json());
app.use(agentPassportMiddleware({ policyId: 'finance.payment.refund.v1' }));

app.post('/api/refunds', (req, res) => {
  res.json({ agent_id: req.agent.agent_id, policyResult: req.policyResult });
});
```

### FastAPI Middleware

```bash
pip install aporthq-middleware-fastapi
```

```python
from fastapi import FastAPI, Request
from aporthq_middleware_fastapi import AgentPassportMiddleware, AgentPassportMiddlewareOptions

app = FastAPI()
app.add_middleware(
    AgentPassportMiddleware,
    options=AgentPassportMiddlewareOptions(policy_id="finance.payment.refund.v1"),
)

@app.post("/api/refunds")
async def get_data(request: Request):
    return {"agent_id": request.state.agent.agent_id}
```

## Supported Policies

All SDKs call `POST /api/verify/policy/{pack_id}`. Supported `pack_id` values (from policy registry):

| Policy Pack | Capability | Min Assurance |
|-------------|------------|---------------|
| agent.session.create.v1 | agent.session.create | L0 |
| agent.tool.register.v1 | agent.tool.register | L0 |
| code.release.publish.v1 | repo.release | L3 |
| code.repository.merge.v1 | repo.pr.create, repo.merge | L2 |
| data.export.create.v1 | data.export | L1 |
| data.file.read.v1 | data.file.read | L0 |
| data.file.write.v1 | data.file.write | L0 |
| data.report.ingest.v1 | data.report.ingest | L2 |
| deliverable.task.complete.v1 | deliverable.task.complete | L0 |
| finance.crypto.trade.v1 | finance.crypto.trade | L3 |
| finance.payment.charge.v1 | payments.charge | L2 |
| finance.payment.payout.v1 | payments.payout | L3 |
| finance.payment.refund.v1 | finance.payment.refund | L2 |
| finance.transaction.execute.v1 | finance.transaction | L3 |
| governance.data.access.v1 | data.access | L3 |
| legal.contract.review.v1 | legal.contract.review | L3 |
| mcp.tool.execute.v1 | mcp.tool.execute | L0 |
| messaging.message.send.v1 | messaging.send | L0 |
| system.command.execute.v1 | system.command.execute | L0 |
| web.browser.v1 | web.browser | L0 |
| web.fetch.v1 | web.fetch | L0 |

For required context fields per policy: `GET /api/policies` or `GET /api/policies/{pack_id}`.

## 🔧 Features

### SDK Features
- **Automatic Header Injection**: Automatically add `X-Agent-Passport-Id` header to requests
- **Agent Verification**: Verify agent passports against the registry
- **Permission Checking**: Check if agents have specific permissions
- **Regional Access Control**: Verify agents are allowed in specific regions
- **Caching**: Built-in caching for verification results
- **Error Handling**: Comprehensive error handling with custom exceptions
- **TypeScript Support**: Full TypeScript definitions for Node.js SDK

### Middleware Features
- **Automatic Verification**: Automatically verify agent passports on requests
- **Permission Enforcement**: Enforce required permissions for routes
- **Regional Access Control**: Restrict access based on agent regions
- **Configurable**: Flexible configuration options
- **Selective Application**: Skip verification for specific paths/methods
- **Error Handling**: Proper HTTP status codes and error messages

## 📋 Transport Profile

All SDKs and middleware implement the [Transport Profile Specification](../spec/transport-profile.md):

### HTTP/Webhooks
```
X-Agent-Passport-Id: <agent_id>
```

### gRPC
```
x-agent-passport-id: <agent_id>
```

### WebSocket/SSE
```
ws://api.example.com/stream?agent_id=ap_a2d10232c6534523812423eec8a1425c4567890abcdef
```

### Message Queues
```json
{
  "MessageAttributes": {
    "agent_id": {
      "StringValue": "ap_a2d10232c6534523812423eec8a1425c4567890abcdef",
      "DataType": "String"
    }
  }
}
```

### Environment Variables
```bash
export AGENT_PASSPORT_ID=ap_a2d10232c6534523812423eec8a1425c4567890abcdef
```

## 🛠️ Development

### Building SDKs

```bash
# Node.js SDK
cd node/
npm install
npm run build
npm test

# Python SDK
cd python/
pip install -e ".[dev]"
pytest
```

### Building Middleware

```bash
# Express.js Middleware
cd ../middleware/express/
npm install
npm run build
npm test

# FastAPI Middleware
cd ../middleware/fastapi/
pip install -e ".[dev]"
pytest
```

## 📚 Documentation

- [Transport Profile Specification](../spec/transport-profile.md) - Complete transport specification
- [Node.js SDK Documentation](./node/README.md) - Node.js SDK documentation
- [Python SDK Documentation](./python/README.md) - Python SDK documentation
- [Express.js Middleware Documentation](../middleware/express/README.md) - Express.js middleware documentation
- [FastAPI Middleware Documentation](../middleware/fastapi/README.md) - FastAPI middleware documentation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License
MIT


---
**Last Updated**: 2025-10-08 14:54:16 UTC
