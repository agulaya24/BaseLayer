# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Base Layer, please report it privately rather than opening a public issue.

**Email:** `aarik@base-layer.ai` with subject line `[SECURITY] <short description>`

Please include:

- A description of the issue and where it surfaces (file/path, command, endpoint).
- Steps to reproduce.
- The impact you believe it has (confidentiality, integrity, availability, or scope).
- Any suggested mitigation if you have one.

You will receive an acknowledgement within 72 hours. We will keep you updated as the issue is investigated and resolved, and will credit you in the changelog if you wish.

## Scope

In scope:

- The Python package (`baselayer`), CLI, and MCP server.
- The pipeline scripts and authoring/composition prompts.
- The provenance verifier (`baselayer verify`) and the citation graph integrity.
- API endpoints exposed at `base-layer.ai` for served specifications.

Out of scope:

- Issues in third-party dependencies (report upstream).
- Issues in the user's own data, API keys, or local environment.
- Vulnerabilities requiring physical access to the user's machine.

## What We Care About

- Prompt injection paths through the extraction or authoring pipelines that could compromise downstream agents.
- Provenance-graph tampering that lets an unsupported claim pass `baselayer verify`.
- Data exfiltration paths from local stores (SQLite, ChromaDB) to external services.
- Unauthenticated access to user-served specifications via the MCP server or HTTP API.

## Disclosure Timeline

We aim to confirm and assess reports within 7 days, ship a fix within 30 days for high-severity issues, and disclose publicly within 90 days unless coordinated otherwise.

Pre-1.0 caveat: this project is pre-release. Security guarantees are best-effort. Report responsibly; we'll respond in kind.
