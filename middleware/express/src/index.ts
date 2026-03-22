/**
 * Express Middleware for Agent Passport Registry
 *
 * This middleware provides framework-specific integration for Express.js
 * while delegating all business logic to the @aporthq/sdk-node package.
 *
 * Key Features:
 * - Agent ID validation with function parameter preference over headers
 * - Policy enforcement using the thin client SDK
 * - Type-safe interfaces for all middleware functions
 * - Simple configuration options
 */

import { Request, Response, NextFunction } from "express";
import { APortClient, PolicyVerifier, AportError } from "@aporthq/sdk-node";

// Extend Express Request type to include agent and policy data
export interface AgentRequest extends Request {
  agent?: {
    agent_id: string;
    [key: string]: any;
  };
  policyResult?: {
    decision_id: string;
    allow: boolean;
    reasons?: Array<{
      code: string;
      message: string;
      severity?: string;
    }>;
    [key: string]: any;
  };
}

export interface AgentPassportMiddlewareOptions {
  baseUrl?: string;
  apiKey?: string;
  timeoutMs?: number;
  failClosed?: boolean;
  skipPaths?: string[];
  policyId?: string;
  /** Use req.body.passport when present (local mode). Default true. */
  passportFromBody?: boolean;
  /** Use req.body.policy when present (pack_id IN_BODY). Default true. */
  policyFromBody?: boolean;
}

export interface PolicyMiddlewareOptions {
  policyId: string;
  agentId?: string;
  context?: Record<string, any>;
}

// Default middleware options
const DEFAULT_OPTIONS = {
  baseUrl: process.env.AGENT_PASSPORT_BASE_URL || "https://api.aport.io",
  apiKey: process.env.AGENT_PASSPORT_API_KEY || undefined,
  timeoutMs: 5000,
  failClosed: true,
  skipPaths: ["/health", "/metrics", "/status"],
  policyId: "",
  passportFromBody: true,
  policyFromBody: true,
};

/**
 * Create APortClient with sensible defaults
 */
function createClient(
  baseUrl?: string,
  apiKey?: string,
  timeoutMs?: number
): APortClient {
  return new APortClient({
    baseUrl: baseUrl || process.env.AGENT_PASSPORT_BASE_URL,
    apiKey: apiKey || process.env.AGENT_PASSPORT_API_KEY,
    timeoutMs: timeoutMs || 5000,
  });
}

/**
 * Extract agent ID from request headers, body.passport, or function parameter
 */
function extractAgentId(
  request: Request,
  providedAgentId?: string,
  passportFromBody = true
): string | null {
  if (providedAgentId) {
    return providedAgentId;
  }
  if (passportFromBody && request.body?.passport?.agent_id) {
    return request.body.passport.agent_id as string;
  }
  return (
    (request.headers["x-agent-passport-id"] as string) ||
    (request.headers["x-agent-id"] as string) ||
    null
  );
}

/**
 * Check if request should be skipped based on path
 */
function shouldSkipRequest(request: Request, skipPaths: string[]): boolean {
  return skipPaths.some((path) => request.path.startsWith(path));
}

/**
 * Create error response
 */
function createErrorResponse(
  res: Response,
  status: number,
  error: string,
  message: string,
  additional?: Record<string, any>
) {
  return res.status(status).json({
    error,
    message,
    ...additional,
  });
}

/**
 * Global middleware that enforces a specific policy on all routes
 */
export function agentPassportMiddleware(
  options: AgentPassportMiddlewareOptions = {}
) {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const client = new APortClient({
    baseUrl: opts.baseUrl,
    apiKey: opts.apiKey,
    timeoutMs: opts.timeoutMs,
  });

  return async (req: AgentRequest, res: Response, next: NextFunction) => {
    try {
      // Skip middleware for certain paths
      if (shouldSkipRequest(req, opts.skipPaths)) {
        return next();
      }

      const usePassportFromBody = opts.passportFromBody !== false;
      const usePolicyFromBody = opts.policyFromBody !== false;
      const bodyPassport = usePassportFromBody ? req.body?.passport : undefined;
      const bodyPolicy = usePolicyFromBody ? req.body?.policy : undefined;

      // Extract agent ID (header or body.passport)
      const agentId = extractAgentId(req, undefined, usePassportFromBody);
      if (!agentId && !bodyPassport) {
        if (opts.failClosed) {
          return createErrorResponse(
            res,
            401,
            "missing_agent_id",
            "Agent ID is required. Provide X-Agent-Passport-Id header or body.passport."
          );
        }
        return next();
      }

      const effectiveAgentId = agentId ?? bodyPassport?.agent_id;

      // If no policy ID and no policy in body, just verify agent exists (or use passport from body)
      if (!opts.policyId && !bodyPolicy) {
        if (bodyPassport) {
          req.agent = { agent_id: bodyPassport.agent_id, ...bodyPassport };
          return next();
        }
        try {
          const passportView = await client.getPassportView(effectiveAgentId!);
          req.agent = {
            agent_id: effectiveAgentId!,
            ...passportView,
          };
          return next();
        } catch (error) {
          if (error instanceof AportError) {
            return createErrorResponse(
              res,
              error.status,
              "agent_verification_failed",
              error.message,
              { agent_id: effectiveAgentId }
            );
          }
          throw error;
        }
      }

      // Build context from body (exclude passport and policy so they are not duplicated)
      const context =
        typeof req.body === "object" && req.body !== null
          ? { ...req.body }
          : {};
      delete context.passport;
      delete context.policy;

      let decision;
      if (bodyPolicy) {
        // Policy in body: use IN_BODY; agent from passport or header
        const agentIdOrPassport = bodyPassport ?? effectiveAgentId!;
        decision = await client.verifyPolicyWithPolicyInBody(
          agentIdOrPassport,
          bodyPolicy,
          context
        );
      } else if (bodyPassport) {
        // Passport in body (local mode)
        decision = await client.verifyPolicyWithPassport(
          bodyPassport,
          opts.policyId!,
          context
        );
      } else {
        // Cloud mode: agent_id only
        decision = await client.verifyPolicy(
          effectiveAgentId!,
          opts.policyId!,
          context
        );
      }

      if (!decision.allow) {
        return createErrorResponse(
          res,
          403,
          "policy_violation",
          "Policy violation",
          {
            agent_id: effectiveAgentId,
            policy_id: opts.policyId ?? bodyPolicy?.id,
            decision_id: decision.decision_id,
            reasons: decision.reasons,
          }
        );
      }

      req.agent = { agent_id: effectiveAgentId! };
      req.policyResult = decision;

      next();
    } catch (error) {
      if (error instanceof AportError) {
        return createErrorResponse(
          res,
          error.status,
          "api_error",
          error.message,
          { reasons: error.reasons }
        );
      }

      console.error("Agent Passport middleware error:", error);
      return createErrorResponse(
        res,
        500,
        "internal_error",
        "Internal server error"
      );
    }
  };
}

/**
 * Route-specific middleware that enforces a specific policy.
 * Supports body.passport (local mode) and body.policy (IN_BODY) when present.
 */
export function requirePolicy(policyId: string, agentId?: string) {
  const client = new APortClient({
    baseUrl: process.env.AGENT_PASSPORT_BASE_URL || "https://api.aport.io",
    apiKey: process.env.AGENT_PASSPORT_API_KEY || undefined,
    timeoutMs: 5000,
  });

  return async (req: AgentRequest, res: Response, next: NextFunction) => {
    try {
      const bodyPassport = req.body?.passport;
      const bodyPolicy = req.body?.policy;
      const extractedAgentId = extractAgentId(req, agentId, true);
      if (!extractedAgentId && !bodyPassport) {
        return createErrorResponse(
          res,
          401,
          "missing_agent_id",
          "Agent ID is required. Provide X-Agent-Passport-Id header, function parameter, or body.passport."
        );
      }

      const context =
        typeof req.body === "object" && req.body !== null
          ? { ...req.body }
          : {};
      delete context.passport;
      delete context.policy;

      let decision;
      if (bodyPolicy) {
        const agentIdOrPassport = bodyPassport ?? extractedAgentId!;
        decision = await client.verifyPolicyWithPolicyInBody(
          agentIdOrPassport,
          bodyPolicy,
          context
        );
      } else if (bodyPassport) {
        decision = await client.verifyPolicyWithPassport(
          bodyPassport,
          policyId,
          context
        );
      } else {
        decision = await client.verifyPolicy(
          extractedAgentId!,
          policyId,
          context
        );
      }

      if (!decision.allow) {
        return createErrorResponse(
          res,
          403,
          "policy_violation",
          "Policy violation",
          {
            agent_id: extractedAgentId ?? bodyPassport?.agent_id,
            policy_id: policyId,
            decision_id: decision.decision_id,
            reasons: decision.reasons,
          }
        );
      }

      req.agent = {
        agent_id: extractedAgentId ?? bodyPassport!.agent_id,
      };
      req.policyResult = decision;

      next();
    } catch (error) {
      if (error instanceof AportError) {
        return createErrorResponse(
          res,
          error.status,
          "api_error",
          error.message,
          { reasons: error.reasons }
        );
      }

      console.error("Policy verification error:", error);
      return createErrorResponse(
        res,
        500,
        "internal_error",
        "Internal server error"
      );
    }
  };
}

/**
 * Route-specific middleware with custom context.
 * Supports body.passport (local mode) and body.policy (IN_BODY) when present.
 */
export function requirePolicyWithContext(
  policyId: string,
  context: Record<string, any>,
  agentId?: string
) {
  const client = new APortClient({
    baseUrl: process.env.AGENT_PASSPORT_BASE_URL || "https://api.aport.io",
    apiKey: process.env.AGENT_PASSPORT_API_KEY || undefined,
    timeoutMs: 5000,
  });

  return async (req: AgentRequest, res: Response, next: NextFunction) => {
    try {
      const bodyPassport = req.body?.passport;
      const bodyPolicy = req.body?.policy;
      const extractedAgentId = extractAgentId(req, agentId, true);
      if (!extractedAgentId && !bodyPassport) {
        return createErrorResponse(
          res,
          401,
          "missing_agent_id",
          "Agent ID is required. Provide X-Agent-Passport-Id header, function parameter, or body.passport."
        );
      }

      const bodyContext =
        typeof req.body === "object" && req.body !== null
          ? { ...req.body }
          : {};
      delete bodyContext.passport;
      delete bodyContext.policy;
      const mergedContext = { ...bodyContext, ...context };

      let decision;
      if (bodyPolicy) {
        const agentIdOrPassport = bodyPassport ?? extractedAgentId!;
        decision = await client.verifyPolicyWithPolicyInBody(
          agentIdOrPassport,
          bodyPolicy,
          mergedContext
        );
      } else if (bodyPassport) {
        decision = await client.verifyPolicyWithPassport(
          bodyPassport,
          policyId,
          mergedContext
        );
      } else {
        decision = await client.verifyPolicy(
          extractedAgentId!,
          policyId,
          mergedContext
        );
      }

      if (!decision.allow) {
        return createErrorResponse(
          res,
          403,
          "policy_violation",
          "Policy violation",
          {
            agent_id: extractedAgentId ?? bodyPassport?.agent_id,
            policy_id: policyId,
            decision_id: decision.decision_id,
            reasons: decision.reasons,
          }
        );
      }

      req.agent = {
        agent_id: extractedAgentId ?? bodyPassport!.agent_id,
      };
      req.policyResult = decision;

      next();
    } catch (error) {
      if (error instanceof AportError) {
        return createErrorResponse(
          res,
          error.status,
          "api_error",
          error.message,
          { reasons: error.reasons }
        );
      }

      console.error("Policy verification error:", error);
      return createErrorResponse(
        res,
        500,
        "internal_error",
        "Internal server error"
      );
    }
  };
}

// Convenience functions for specific policies
export const requireRefundPolicy = (agentId?: string) =>
  requirePolicy("finance.payment.refund.v1", agentId);
export const requireDataExportPolicy = (agentId?: string) =>
  requirePolicy("data.export.create.v1", agentId);
export const requireMessagingPolicy = (agentId?: string) =>
  requirePolicy("messaging.message.send.v1", agentId);
export const requireRepositoryPolicy = (agentId?: string) =>
  requirePolicy("code.repository.merge.v1", agentId);
export const requireDeliverableTaskCompletePolicy = (agentId?: string) =>
  requirePolicy("deliverable.task.complete.v1", agentId);

/**
 * Get decision token for near-zero latency validation
 */
export function getDecisionToken(
  agentId: string,
  policyId: string,
  context: Record<string, any> = {}
) {
  const client = createClient();
  return client.getDecisionToken(agentId, policyId, context);
}

/**
 * Validate decision token via server
 */
export function validateDecisionToken(token: string) {
  const client = createClient();
  return client.validateDecisionToken(token);
}

/**
 * Validate decision token locally using JWKS
 */
export function validateDecisionTokenLocal(token: string) {
  const client = createClient();
  return client.validateDecisionTokenLocal(token);
}

/**
 * Get passport view for debugging/about pages
 */
export function getPassportView(agentId: string) {
  const client = createClient();
  return client.getPassportView(agentId);
}

/**
 * Get JWKS for local token validation
 */
export function getJwks() {
  const client = createClient();
  return client.getJwks();
}

/**
 * Direct policy verification using PolicyVerifier
 */
export function verifyRefund(
  agentId: string,
  context: {
    amount: number;
    currency: string;
    order_id: string;
    reason?: string;
  },
  idempotencyKey?: string
) {
  const client = createClient();
  const verifier = new PolicyVerifier(client);
  return verifier.verifyRefund(agentId, context, idempotencyKey);
}

export function verifyRelease(
  agentId: string,
  context: {
    repository: string;
    version: string;
    files: string[];
  },
  idempotencyKey?: string
) {
  const client = createClient();
  const verifier = new PolicyVerifier(client);
  return verifier.verifyRelease(agentId, context, idempotencyKey);
}

export function verifyDataExport(
  agentId: string,
  context: {
    data_types: string[];
    destination: string;
    format: string;
  },
  idempotencyKey?: string
) {
  const client = createClient();
  const verifier = new PolicyVerifier(client);
  return verifier.verifyDataExport(agentId, context, idempotencyKey);
}

export function verifyMessaging(
  agentId: string,
  context: {
    channel: string;
    message: string;
    mentions?: string[];
  },
  idempotencyKey?: string
) {
  const client = createClient();
  const verifier = new PolicyVerifier(client);
  return verifier.verifyMessaging(agentId, context, idempotencyKey);
}

export function verifyRepository(
  agentId: string,
  context: {
    operation: "create_pr" | "merge";
    repository: string;
    base_branch?: string;
    pr_size_kb?: number;
    file_paths?: string[];
    github_actor?: string;
    title?: string;
    description?: string;
  },
  idempotencyKey?: string
) {
  const client = createClient();
  const verifier = new PolicyVerifier(client);
  return verifier.verifyRepository(agentId, context, idempotencyKey);
}

// Re-export SDK types for convenience
export { AportError } from "@aporthq/sdk-node";
export type {
  PolicyVerificationResponse,
  PolicyVerificationRequestBody,
  PolicyPack,
  APortClientOptions,
  Jwks,
  Decision,
  DecisionReason,
  VerificationContext,
  PolicyVerificationRequest,
  PassportData,
} from "@aporthq/sdk-node";
