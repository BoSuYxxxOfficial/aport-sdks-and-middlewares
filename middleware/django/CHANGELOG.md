# Changelog

All notable changes to the Django middleware will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.4] - 2026-05-11

### Added
- Initial Django middleware package.
- Global Agent Passport middleware for Django `MIDDLEWARE`.
- `require_policy(policy_id, agent_id=None)` view decorator.
- Settings and environment configuration.
- JSON error responses for missing agents, policy violations, SDK errors, and internal errors.
- Django test client coverage and a simple example project.
