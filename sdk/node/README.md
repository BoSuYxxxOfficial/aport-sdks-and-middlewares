# Agent Passport Node.js SDK

A production-grade thin Node.js SDK for The Passport for AI Agents, providing easy integration with agent authentication and policy verification via API calls. All policy logic, counters, and enforcement happen on the server side.

## Features

- ✅ **Thin Client Architecture** - No policy logic, no Cloudflare imports, no counters
- ✅ **Production Ready** - Timeouts, retries, proper error handling, Server-Timing support
- ✅ **Type Safe** - Full TypeScript support with comprehensive type definitions
- ✅ **Idempotency Support** - Both header and body idempotency key support
- ✅ **Local Token Validation** - JWKS support for local decision token validation
- ✅ **Multiple Environments** - Production, sandbox, and self-hosted enterprise support
- ✅ **Zero Dependencies** - Uses native Node.js 18+ fetch API

## Installation

```bash
npm install @aporthq/sdk-node
```

**Requirements:** Node.js 18.0.0 or higher

## 💰 Amount Handling

**All monetary amounts must be passed in cents (minor currency units).**

### Examples:
- `$5.00` → `500` cents
- `$100.00` → `10000` cents  
- `$0.50` → `50` cents

### API Fields:
- **`amount`**: Integer value in cents (e.g., `500` for $5.00) - **RECOMMENDED**
- **`amount_minor`**: Integer value in cents (e.g., `500` for $5.00) - **LEGACY, use `amount` instead**

## Quick Start

```javascript
import { APortClient, PolicyVerifier, AportError } from '@aporthq/sdk-node';

// Initialize client for production
const client = new APortClient({
  baseUrl: 'https://api.aport.io', // Production API
  apiKey: 'your-api-key', // Optional
  timeoutMs: 800 // Optional: Request timeout (default: 800ms)
});

// Or for sandbox/testing
const sandboxClient = new APortClient({
  baseUrl: 'https://sandbox.aport.io', // Sandbox API
  apiKey: 'your-sandbox-key'
});

// Or for self-hosted enterprise
const enterpriseClient = new APortClient({
  baseUrl: 'https://your-company.aport.io', // Your self-hosted instance
  apiKey: 'your-enterprise-key'
});

// Generic policy verification - works with any policy
try {
  const decision = await client.verifyPolicy(
    'your-agent-id',
    'finance.payment.refund.v1', // Any policy from ./policies
    {
      amount: 1000,  // Amount in cents ($10.00)
      currency: 'USD',
      order_id: 'order_123',
      reason: 'defective'
    },
    'unique-key-123' // Optional idempotency key
  );

  if (decision.allow) {
    console.log('✅ Policy verification passed!');
    console.log(`Decision ID: ${decision.decision_id}`);
    console.log(`Assurance Level: ${decision.assurance_level}`);
  } else {
    console.log('❌ Policy verification failed!');
    decision.reasons?.forEach(reason => {
      console.log(`  - [${reason.severity}] ${reason.code}: ${reason.message}`);
    });
  }
} catch (error) {
  if (error instanceof AportError) {
    console.error(`API Error ${error.status}:`, error.message);
    console.error('Reasons:', error.reasons);
    console.error('Decision ID:', error.decision_id);
  } else {
    console.error('Policy verification failed:', error.message);
  }
}
```

## Environments

The SDK supports different environments through the `baseUrl` parameter:

- **Production**: `https://api.aport.io` - The main APort API
- **Sandbox**: `https://sandbox.aport.io` - Testing environment with mock data
- **Self-hosted**: `https://your-domain.com` - Your own APort instance

You can also host your own APort service for complete control over policy verification and data privacy.

## API Reference

### `APortClient`

The core client for interacting with the APort API endpoints.

#### `constructor(options: APortClientOptions)`
Initializes the APort client.
- `options.baseUrl` (string): The base URL of your APort API (e.g., `https://api.aport.io`).
- `options.apiKey` (string, optional): Your API Key for authenticated requests.
- `options.timeoutMs` (number, optional): Request timeout in milliseconds (default: 800ms).

#### `verifyPolicy(agentId: string, policyId: string, context?: Record<string, any>, idempotencyKey?: string, options?: { passport?: PassportData; policy?: PolicyPack }): Promise<PolicyVerificationResponse>`
Verifies a policy against an agent by calling the `/api/verify/policy/:pack_id` endpoint. Optionally pass `passport` and/or `policy` in the request body (local/dynamic mode).
- `agentId` (string): The ID of the agent.
- `policyId` (string): The ID of the policy pack (e.g., `finance.payment.refund.v1`, `deliverable.task.complete.v1`, `code.release.publish.v1`).
- `context` (Record<string, any>, optional): The policy-specific context data.
- `idempotencyKey` (string, optional): An optional idempotency key for the request.
- `options` (object, optional): `{ passport?: PassportData; policy?: PolicyPack }` to send passport/policy in body.

#### `verifyPolicyWithPassport(passport: PassportData, policyId: string, context?: Record<string, any>, idempotencyKey?: string): Promise<PolicyVerificationResponse>`
Verifies a policy using a passport in the request body (local mode; no registry fetch). Calls `/api/verify/policy/:pack_id` with `body.passport`.

#### `verifyPolicyWithPolicyInBody(agentIdOrPassport: string | PassportData, policy: PolicyPack, context?: Record<string, any>, idempotencyKey?: string): Promise<PolicyVerificationResponse>`
Verifies using a policy pack in the request body (pack_id = IN_BODY). Pass either `agentId` (cloud) or `PassportData` (local).

#### `getDecisionToken(agentId: string, policyId: string, context?: Record<string, any>): Promise<string>`
Retrieves a short-lived decision token for near-zero latency local validation. Calls `/api/verify/token/:pack_id`.

#### `validateDecisionToken(token: string): Promise<PolicyVerificationResponse>`
Validates a decision token via server (for debugging). Calls `/api/verify/token/validate`.

#### `getPassportView(agentId: string): Promise<any>`
Retrieves a small, cacheable view of an agent's passport (limits, assurance, status) for display purposes (e.g., about pages, debugging). Calls `/api/passports/:id/verify_view`.

#### `validateDecisionTokenLocal(token: string): Promise<PolicyVerificationResponse>`
Validates a decision token locally using JWKS (recommended for production). Falls back to server validation if JWKS unavailable.

#### `getJwks(): Promise<Jwks>`
Retrieves the JSON Web Key Set for local token validation. Cached for 5 minutes.

### `PolicyVerifier`

A convenience class that wraps `APortClient` to provide policy-specific verification methods.

#### `constructor(client: APortClient)`
Initializes the PolicyVerifier with an `APortClient` instance.

#### `verifyRefund(agentId: string, context: { amount: number; currency: string; order_id: string; reason?: string; }, idempotencyKey?: string): Promise<PolicyVerificationResponse>`
Verifies the `finance.payment.refund.v1` policy.

#### `verifyRepository(agentId: string, context: { operation: "create_pr" | "merge"; repository: string; base_branch?: string; pr_size_kb?: number; file_paths?: string[]; github_actor?: string; title?: string; description?: string; }, idempotencyKey?: string): Promise<PolicyVerificationResponse>`
Verifies the `code.repository.merge.v1` policy.

#### `verifyDeliverableTaskComplete(agentId: string, context: { task_id: string; output_type: "code" | "document" | "analysis" | "plan" | "data" | "other"; criteria_attestations: Array<{ criterion_id: string; met: boolean; evidence: string }>; summary?: string; tests_passing?: boolean; reviewer_agent_id?: string; author_agent_id?: string; output_content?: string; }, idempotencyKey?: string): Promise<PolicyVerificationResponse>`
Verifies the `deliverable.task.complete.v1` policy (task completion gate).

#### Additional Policy Methods
The `PolicyVerifier` also includes convenience methods for other policies:
- `verifyRelease()` - Verifies the `code.release.publish.v1` policy
- `verifyDataExport()` - Verifies the `data.export.create.v1` policy  
- `verifyMessaging()` - Verifies the `messaging.message.send.v1` policy

These methods follow the same pattern as `verifyRefund()` and `verifyRepository()`.

## Error Handling

The SDK throws `AportError` objects for API request failures with detailed error information.

```javascript
import { AportError } from '@aporthq/sdk-node';

try {
  await client.verifyPolicy("invalid-agent", "finance.payment.refund.v1", {});
} catch (error) {
  if (error instanceof AportError) {
    console.error(`Status: ${error.status}`);
    console.error(`Message: ${error.message}`);
    console.error(`Reasons:`, error.reasons);
    console.error(`Decision ID:`, error.decision_id);
    console.error(`Server Timing:`, error.serverTiming);
  } else {
    console.error("Unexpected error:", error.message);
  }
}
```

### Error Types

- **`AportError`**: API request failures with status codes, reasons, and decision IDs
- **Timeout Errors**: 408 status with `TIMEOUT` reason code
- **Network Errors**: 0 status with `NETWORK_ERROR` reason code

## Production Features

### Idempotency Support
The SDK supports idempotency keys in both the request body and the `Idempotency-Key` header (header takes precedence).

```javascript
const decision = await client.verifyPolicy(
  "agent-123",
  "finance.payment.refund.v1",
  { amount: 100, currency: "USD" },  // Amount in cents ($1.00)
  "unique-idempotency-key" // Sent in both header and body
);
```

### Server-Timing Support
The SDK automatically captures and exposes Server-Timing headers for performance monitoring.

```javascript
const decision = await client.verifyPolicy("agent-123", "finance.payment.refund.v1", {});
console.log("Server timing:", decision._meta?.serverTiming);
// Example: "cache;dur=5,db;dur=12"
```

### Local Token Validation
For high-performance scenarios, use local token validation with JWKS:

```javascript
// Get JWKS (cached for 5 minutes)
const jwks = await client.getJwks();

// Validate token locally (no server round-trip)
const decision = await client.validateDecisionTokenLocal(token);
```

### Timeout and Retry Configuration
Configure timeouts and retry behavior:

```javascript
const client = new APortClient({
  baseUrl: "https://api.aport.io",
  apiKey: "your-key",
  timeoutMs: 500 // 500ms timeout
});
```

## TypeScript Support

The SDK includes full TypeScript definitions for all classes, interfaces, and types.

```typescript
import { APortClient, APortClientOptions, PolicyVerificationResponse } from '@aporthq/sdk-node';

const options: APortClientOptions = {
  baseUrl: 'https://api.aport.io',
  apiKey: 'my-secret-key',
  timeoutMs: 800
};

const client: APortClient = new APortClient(options);

const decision: PolicyVerificationResponse = await client.verifyPolicy(
  "agent_123", 
  "finance.payment.refund.v1", 
  { amount: 500, currency: "EUR" }  // Amount in cents (€5.00)
);
```

## License

MIT