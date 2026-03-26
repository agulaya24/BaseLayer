# Web Security Compliance Requirements
## Base Layer File Processing Web Service

**Service description:** Stateless web service that accepts ChatGPT conversation export files (ZIP containing JSON), processes them through Anthropic's API, and returns behavioral identity models. No login/accounts. Handles highly personal data (AI conversation histories).

**Document purpose:** Build checklist. Every item has an applicability ruling and a priority tier.

**Priority tiers:**
- **MUST** — Required for launch. Non-negotiable.
- **SHOULD** — Required before scaling to public users. Acceptable technical debt at launch only if acknowledged.
- **NICE** — Maturity items. Build toward them, do not block on them.

---

## Table of Contents

1. [OWASP Top 10 (2021)](#1-owasp-top-10-2021)
2. [OWASP API Security Top 10 (2023)](#2-owasp-api-security-top-10-2023)
3. [Security Headers](#3-security-headers)
4. [File Upload Security](#4-file-upload-security)
5. [GDPR Compliance](#5-gdpr-compliance)
6. [SOC 2 Readiness](#6-soc-2-readiness)
7. [Dependency Security](#7-dependency-security)
8. [Rate Limiting and Abuse Prevention](#8-rate-limiting-and-abuse-prevention)
9. [Implementation Priority Matrix](#9-implementation-priority-matrix)

---

## 1. OWASP Top 10 (2021)

### A01: Broken Access Control

**Applies:** YES

**What it is:** Failures in enforcing policies such that users cannot act outside their intended permissions. Includes unauthorized access to files, URL manipulation, CORS misconfiguration, and elevation of privilege.

**Our specific risks:**
- Download URLs for completed identity models could be guessable or enumerable
- Processed files stored temporarily on disk could be accessed by other requests
- Direct object references in status-check or download endpoints

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Unguessable result URLs | Use cryptographically random UUIDs (UUIDv4, 128-bit) for all job IDs and download tokens. Never sequential IDs. | MUST |
| Time-limited download URLs | Results expire and are deleted after a short TTL (e.g., 15 minutes). Signed URLs with HMAC if using cloud storage. | MUST |
| Deny by default | No directory listing on any path. Return 404 (not 403) for nonexistent resources to prevent enumeration. | MUST |
| File isolation | Each upload gets its own temp directory, created with restrictive permissions (0700). Clean up on completion or timeout. | MUST |
| CORS lockdown | Access-Control-Allow-Origin set to the exact frontend domain. Never `*`. | MUST |
| No path parameters for file access | Never accept user-supplied file paths. Map job IDs to internal paths server-side. | MUST |

---

### A02: Cryptographic Failures

**Applies:** YES

**What it is:** Failures related to cryptography (or lack thereof) that lead to exposure of sensitive data. Includes cleartext transmission, weak algorithms, poor key management.

**Our specific risks:**
- Conversation data in transit between user's browser and our server
- Conversation data in transit between our server and Anthropic's API
- Conversation data at rest during processing (even if ephemeral)
- Result files at rest before download

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| TLS 1.2+ everywhere | Enforce HTTPS with HSTS. No HTTP fallback. TLS 1.2 minimum, prefer 1.3. | MUST |
| TLS to Anthropic API | Verify Anthropic SDK uses TLS. It does by default (HTTPS endpoints). Confirm no custom HTTP overrides. | MUST |
| No data at rest encryption needed (ephemeral) | Files exist only during processing, deleted immediately after. If processing takes >5 minutes, encrypt temp files with per-job AES-256 keys held only in memory. | SHOULD |
| No PII in URLs | Job IDs in URLs must not contain or encode any user data. Pure random tokens. | MUST |
| No PII in logs | See A09. Conversation content must never appear in application logs. | MUST |
| Certificate pinning | Not required for web service. Anthropic SDK handles its own TLS. | NICE |

---

### A03: Injection

**Applies:** YES

**What it is:** Hostile data sent to an interpreter as part of a command or query. Includes SQL injection, XSS, command injection, and file path injection.

**Our specific risks:**
- JSON parsing of ChatGPT export files (malicious JSON content)
- File names within ZIP archives (path traversal)
- Any user-supplied data reflected in API responses (XSS)
- Prompt injection via conversation content sent to Anthropic API

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Strict JSON parsing | Use Python's `json.loads()` with no custom deserializers. Reject malformed JSON immediately. Do not use `eval()` or `yaml.load()` on user data. | MUST |
| Input validation on JSON structure | Validate expected ChatGPT export schema: must have `conversations` array, each with `mapping` containing message nodes. Reject anything that does not conform. Define a JSON Schema and validate against it. | MUST |
| Filename sanitization | See File Upload Security section. Strip all path components from ZIP entries. | MUST |
| Output encoding | All API responses are JSON with `Content-Type: application/json`. No HTML rendering of user data. Set `X-Content-Type-Options: nosniff`. | MUST |
| No shell commands | Never pass user data to subprocess, os.system, or shell commands. | MUST |
| Prompt injection awareness | Conversation content is passed to Anthropic API as data, not as system instructions. Wrap user content in clear delimiters (e.g., XML tags). Anthropic's Claude has built-in prompt injection resistance, but defense in depth applies. | SHOULD |
| No SQL | Service is stateless with no database. If any datastore is added later, use parameterized queries only. | MUST (if applicable) |

---

### A04: Insecure Design

**Applies:** YES

**What it is:** A broad category representing flaws in the design itself, not just implementation bugs. Calls for threat modeling, secure design patterns, and reference architectures.

**Our specific risks:**
- Service designed without abuse modeling (someone uploads 10,000 files to drain Anthropic credits)
- No authentication means no accountability for abuse
- Ephemeral design is actually a strength (less to protect), but must be truly ephemeral

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Threat model | Document: (1) Who are the adversaries? (abuse, data theft, service disruption) (2) What are the assets? (Anthropic API credits, user conversation data, service availability) (3) What are the attack surfaces? (upload endpoint, status endpoint, download endpoint) | MUST |
| Abuse scenario matrix | Model at minimum: credit drain, data exfiltration, DoS, ZIP bomb, prompt injection, enumeration of other users' results | MUST |
| Ephemeral-by-design verification | Audit that no user data persists after job completion. Temp files, logs, error reports, debug output — all scrubbed. Automated test that verifies cleanup. | MUST |
| Cost ceiling | Hard cap on Anthropic API spend per hour/day. Alert at 50% of ceiling. Kill switch that disables uploads when ceiling is hit. | MUST |
| Separation of concerns | Upload handling, file validation, API processing, and result delivery should be separate modules with clear boundaries. File validation must complete before any API call. | SHOULD |

---

### A05: Security Misconfiguration

**Applies:** YES

**What it is:** Missing security hardening, unnecessary features enabled, default accounts, overly verbose error messages, misconfigured HTTP headers.

**Our specific risks:**
- Default server configurations exposing stack traces
- Missing security headers
- Debug mode accidentally left on in production
- CORS too permissive

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Production configuration checklist | DEBUG=False, no stack traces in responses, no verbose error messages to clients. Generic error messages only ("Processing failed" not "KeyError in line 47 of extract.py"). | MUST |
| Security headers | See Section 3 (complete list). | MUST |
| Minimize server fingerprinting | Remove `Server` and `X-Powered-By` headers. Do not expose framework/language/version. | MUST |
| Disable unnecessary HTTP methods | Only allow POST (upload), GET (status, download). Return 405 Method Not Allowed for everything else. No PUT, DELETE, PATCH, OPTIONS (except for CORS preflight). | MUST |
| Environment variable management | API keys in environment variables or secrets manager, never in code, config files, or version control. | MUST |
| Regular configuration review | Before each deployment, verify production config matches security baseline. | SHOULD |

---

### A06: Vulnerable and Outdated Components

**Applies:** YES

**What it is:** Using components (libraries, frameworks) with known vulnerabilities. Includes not knowing versions in use, not scanning for vulnerabilities, not updating in a timely manner.

**Our specific risks:**
- Python dependencies (FastAPI/Flask, Anthropic SDK, etc.)
- Frontend dependencies (if any JavaScript framework)
- Transitive dependencies we do not directly control

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Dependency inventory | Maintain `requirements.txt` or `pyproject.toml` with pinned versions. Generate `pip freeze` output and store in repo. | MUST |
| Automated vulnerability scanning | Run `pip-audit` in CI/CD on every push. Fail the build on HIGH/CRITICAL findings. | MUST |
| GitHub Dependabot | Enable Dependabot alerts and security updates for both Python and npm ecosystems. | MUST |
| Update cadence | Review and update dependencies monthly. Apply security patches within 48 hours of disclosure. | SHOULD |
| Minimize dependency surface | Audit each dependency: is it necessary? Can the standard library handle it? Fewer dependencies = smaller attack surface. | SHOULD |

See Section 7 for detailed dependency security guidance.

---

### A07: Identification and Authentication Failures

**Applies:** PARTIAL

**What it is:** Weaknesses in authentication mechanisms. Includes weak passwords, credential stuffing, session management flaws.

**Our specific risks:**
- No user authentication by design (stateless, anonymous)
- BUT: job tokens function as bearer credentials for download access
- API key for Anthropic must be protected server-side

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Job tokens as bearer credentials | Treat job IDs/download tokens with the same care as session tokens: cryptographically random, sufficient entropy (128+ bits), short-lived. | MUST |
| No credential exposure | Anthropic API key never exposed to client. All API calls server-side only. | MUST |
| Rate limit token generation | Prevent rapid-fire job creation from a single source. See Section 8. | MUST |
| Future: optional authentication | If accounts are added later, use established auth libraries (OAuth2, OIDC). Never roll your own. Bcrypt/Argon2 for passwords. | NICE |

---

### A08: Software and Data Integrity Failures

**Applies:** YES

**What it is:** Code and infrastructure that does not protect against integrity violations. Includes insecure CI/CD pipelines, auto-updates without integrity verification, serialization flaws.

**Our specific risks:**
- Supply chain attacks on Python packages
- Integrity of the ChatGPT export file (is it actually from ChatGPT, or crafted?)
- CDN integrity for frontend assets
- CI/CD pipeline security

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| Subresource Integrity (SRI) | If loading any JS/CSS from CDN, use SRI hashes. `<script src="..." integrity="sha384-..." crossorigin="anonymous">` | MUST |
| Lock file integrity | Commit `package-lock.json` and `requirements.txt` (or lock file) to version control. Verify checksums during install. Use `pip install --require-hashes`. | SHOULD |
| No deserialization of untrusted data | Never use `pickle`, `marshal`, or similar on uploaded data. JSON only. | MUST |
| CI/CD hardening | Pin GitHub Actions to SHA (not tags). Use least-privilege tokens. Require reviews on deployment workflows. | SHOULD |
| Input file integrity | We cannot verify ChatGPT export authenticity (no digital signature from OpenAI). Validate structure only. Document this limitation. | MUST (document) |

---

### A09: Security Logging and Monitoring Failures

**Applies:** YES

**What it is:** Insufficient logging, detection, and response capabilities. Includes not logging security events, not monitoring for breaches, logs that contain sensitive data.

**Our specific risks:**
- Logging conversation content (PII exposure in logs)
- Not logging abuse attempts (rate limit hits, invalid uploads)
- No alerting on anomalous usage patterns

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| **WHAT TO LOG** | Job creation (timestamp, source IP hash, file size), job completion/failure (duration, error category), rate limit triggers, invalid file rejections (reason), download events, API cost per job | MUST |
| **WHAT NOT TO LOG** | Conversation content, file contents, extracted facts, identity model output, full IP addresses (hash or truncate), Anthropic API request/response bodies | MUST |
| Structured logging | JSON-formatted logs with consistent fields: timestamp, event_type, job_id, severity. No string concatenation of user data into log messages. | MUST |
| Log retention | 90 days for operational logs. Ensure log storage itself is access-controlled. | SHOULD |
| Alerting | Alert on: >N failed uploads/hour from single source, API cost exceeding threshold, error rate spike, any 500-level error rate >5% | SHOULD |
| Audit trail | Immutable record of: when data was received, when processing started/ended, when data was deleted. Proves ephemeral claim. | MUST |

---

### A10: Server-Side Request Forgery (SSRF)

**Applies:** PARTIAL

**What it is:** Web application fetches a remote resource based on user-supplied URL without validation, allowing attackers to reach internal services.

**Our specific risks:**
- We do NOT fetch URLs from user input (files are uploaded directly)
- We DO make outbound calls to Anthropic API (fixed, hardcoded endpoint)
- Risk is LOW but not zero if any URL parsing of conversation content occurs

**Implementation guidance:**
| Control | Detail | Priority |
|---------|--------|----------|
| No user-supplied URLs | Do not fetch any URL from uploaded content. If conversation data contains URLs, treat as plain text only. | MUST |
| Allowlist outbound calls | Only allow outbound HTTPS to `api.anthropic.com`. If using cloud metadata, block access to 169.254.169.254 (AWS), 100.100.100.200 (Azure), metadata.google.internal. | SHOULD |
| Network segmentation | Processing containers should have egress restricted to Anthropic API only. No access to internal services. | SHOULD |

---

## 2. OWASP API Security Top 10 (2023)

### API1: Broken Object Level Authorization (BOLA)

**Applies:** YES
**Priority:** MUST

**Risk:** Attacker guesses or enumerates job IDs to access other users' results.

**Controls:**
- UUIDv4 for all job identifiers (2^122 bits of randomness — practically unguessable)
- No sequential or timestamp-based IDs
- Jobs are isolated: each job ID maps to exactly one upload, one result
- Jobs expire and are deleted after TTL (15 min)
- Return 404 (not 403) for all invalid job IDs — no information leakage about existence

---

### API2: Broken Authentication

**Applies:** PARTIAL
**Priority:** MUST

**Risk:** No authentication by design, but job tokens are de facto bearer credentials.

**Controls:**
- Job tokens generated with `secrets.token_urlsafe(32)` (256 bits)
- Tokens are single-use for download (invalidated after first successful download, or after TTL)
- No API keys issued to clients
- Server-side Anthropic API key protected via environment variables

---

### API3: Broken Object Property Level Authorization

**Applies:** PARTIAL
**Priority:** SHOULD

**Risk:** API responses could leak internal properties (internal timestamps, processing metadata, server paths).

**Controls:**
- Explicit response schemas: only return `{job_id, status, result_url}` — nothing else
- No internal fields in API responses (no server paths, no processing details, no error stack traces)
- Use a response serializer/schema (Pydantic model in FastAPI) that whitelist-filters output fields

---

### API4: Unrestricted Resource Consumption

**Applies:** YES — this is a PRIMARY threat
**Priority:** MUST

**Risk:** Attacker uploads large/many files to exhaust server resources or drain Anthropic API credits.

**Controls:**
- Max upload file size: 50MB compressed (enforced at reverse proxy AND application level)
- Max decompressed size: 500MB (enforced during extraction)
- Max concurrent jobs per IP: 3
- Max jobs per IP per hour: 10
- Max jobs per IP per day: 25
- Anthropic API cost cap: hard ceiling per hour and per day
- Request timeout: 30 seconds for upload, 300 seconds for processing
- Queue depth limit: reject new jobs when queue exceeds capacity

---

### API5: Broken Function Level Authorization

**Applies:** PARTIAL
**Priority:** MUST

**Risk:** Accessing admin or internal endpoints.

**Controls:**
- No admin endpoints exposed. Admin functions (if any) on a separate internal service/port
- Only 3 public endpoints: POST /upload, GET /status/{id}, GET /download/{id}
- All other paths return 404
- No endpoint discovery (no OpenAPI/Swagger in production unless explicitly decided)

---

### API6: Unrestricted Access to Sensitive Business Flows

**Applies:** YES
**Priority:** MUST

**Risk:** Automated abuse of the processing pipeline — bots submitting thousands of requests to drain API credits or scrape the service.

**Controls:**
- Rate limiting (see Section 8)
- CAPTCHA or proof-of-work challenge on upload endpoint (SHOULD for launch, MUST for scale)
- Monitoring for automated patterns: identical file sizes, rapid sequential submissions, missing referrer headers
- Consider requiring email for job notification (optional, adds friction but enables accountability)

---

### API7: Server Side Security Misconfiguration

**Applies:** YES
**Priority:** MUST

**Same as OWASP Top 10 A05.** See that section.

Additional API-specific controls:
- Disable TRACE/TRACK HTTP methods
- Set appropriate CORS headers for the API (allow only the frontend origin)
- Remove default error pages

---

### API8: Lack of Protection from Automated Threats

**Applies:** YES
**Priority:** SHOULD

**Risk:** Bots, credential stuffing (N/A for us), scraping, denial of inventory.

**Controls:**
- Rate limiting with sliding window (not just fixed window — prevents burst-at-boundary attacks)
- Fingerprinting: combine IP + User-Agent + Accept-Language for more granular rate limiting
- Consider Cloudflare Bot Management or similar WAF for production

---

### API9: Improper Inventory Management

**Applies:** PARTIAL
**Priority:** SHOULD

**Risk:** Old API versions, undocumented endpoints, forgotten debug endpoints.

**Controls:**
- Single API version at launch (no /v1/ prefix needed yet, but plan for it)
- No debug or test endpoints in production builds
- API inventory document maintained alongside code
- Automated test that verifies only expected endpoints respond with 200

---

### API10: Unsafe Consumption of APIs

**Applies:** YES
**Priority:** MUST

**Risk:** Our service consumes the Anthropic API. If Anthropic's response is malformed or contains unexpected content, we must handle it safely.

**Controls:**
- Validate Anthropic API response structure before processing (check for expected fields)
- Set timeouts on Anthropic API calls (do not wait indefinitely)
- Handle Anthropic API errors gracefully (429, 500, 503) with exponential backoff
- Do not blindly pass Anthropic response content into templates or HTML
- Pin Anthropic SDK version; test upgrades before deploying

---

## 3. Security Headers

All headers below apply to every HTTP response from the service.

### Required Headers (MUST)

| Header | Recommended Value | Purpose |
|--------|-------------------|---------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Forces HTTPS for 2 years. Submit to HSTS preload list. |
| `Content-Security-Policy` | `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests` | Prevents XSS, clickjacking, and data injection. Strict: default-src 'none' blocks everything not explicitly allowed. |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type sniffing. Critical for file downloads. |
| `X-Frame-Options` | `DENY` | Prevents clickjacking. Redundant with CSP frame-ancestors but provides legacy browser support. |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer information leakage. Use `no-referrer` if no analytics needed. |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()` | Disables browser features we do not use. Reduces attack surface. |
| `X-XSS-Protection` | `0` | Disabled. Modern browsers should use CSP instead. Legacy XSS filters can introduce vulnerabilities. Set to 0, not 1. |
| `Cache-Control` | `no-store, no-cache, must-revalidate` (for API responses and downloads) | Prevents caching of sensitive data. Browser and proxy caches must not store conversation data or identity models. |
| `Content-Type` | `application/json; charset=utf-8` (for API), `application/octet-stream` (for downloads) | Explicit content type prevents MIME confusion. |

### Cross-Origin Headers (MUST)

| Header | Recommended Value | Purpose |
|--------|-------------------|---------|
| `Access-Control-Allow-Origin` | `https://yourdomain.com` (exact origin, never `*`) | CORS: only allow requests from our frontend. |
| `Access-Control-Allow-Methods` | `POST, GET, OPTIONS` | CORS: only allow methods we use. |
| `Access-Control-Allow-Headers` | `Content-Type, X-Request-ID` | CORS: only allow headers we need. |
| `Access-Control-Max-Age` | `86400` | Cache preflight responses for 24 hours. Reduces OPTIONS requests. |
| `Cross-Origin-Opener-Policy` | `same-origin` | Prevents cross-origin window references. Mitigates Spectre-class attacks. |
| `Cross-Origin-Resource-Policy` | `same-origin` | Prevents cross-origin embedding of our resources. |
| `Cross-Origin-Embedder-Policy` | `require-corp` | Restricts cross-origin resource loading. Enables process isolation in browsers. |

### Download-Specific Headers (MUST)

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Disposition` | `attachment; filename="identity_model.md"` | Forces download, prevents browser rendering of result files. |
| `X-Content-Type-Options` | `nosniff` | Repeated here for emphasis: critical on download endpoints. |
| `Cache-Control` | `no-store` | Result files must not be cached. |

---

## 4. File Upload Security

This is the highest-risk surface of the application. ChatGPT exports are ZIP files containing JSON. Every validation must pass before any processing begins.

### 4.1 ZIP Bomb Protection

**Applies:** YES
**Priority:** MUST

| Control | Implementation | Detail |
|---------|---------------|--------|
| Compressed size limit | 50MB max | Enforce at reverse proxy (nginx: `client_max_body_size 50m`) AND application layer. Reject before reading into memory. |
| Decompressed size limit | 500MB max | Track cumulative extracted size during extraction. Abort immediately if exceeded. Do NOT trust the `file_size` field in ZIP headers (can be spoofed). |
| Compression ratio limit | Max 100:1 ratio | If any single file in the ZIP has compress_size > 0 and file_size/compress_size > 100, reject. A normal ChatGPT export is ~3:1 to 10:1. |
| Nested archive rejection | No ZIP-within-ZIP | If any extracted file has a .zip, .gz, .tar, .7z, .rar extension or ZIP magic bytes, reject the entire upload. |
| File count limit | Max 50 files in archive | ChatGPT exports typically contain 1-3 files. More than 50 is suspicious. |
| Streaming extraction | Do not extract to disk, then validate | Use Python's `zipfile.ZipFile` in streaming mode. Check each entry BEFORE writing. Use `safezip` library for hardened extraction. |
| Memory limits | Process-level memory limit | Set via container/cgroup (e.g., 512MB). OOM-kill before a ZIP bomb can crash the host. |

### 4.2 Path Traversal Prevention

**Applies:** YES
**Priority:** MUST

| Control | Implementation |
|---------|---------------|
| Strip path components | For every ZIP entry, extract only `os.path.basename(entry.filename)`. Discard all directory components. |
| Reject dangerous names | Reject any entry where the filename contains `..`, starts with `/`, or contains null bytes (`\x00`). |
| Resolve and verify | After constructing the target path: `resolved = os.path.realpath(target)`. Verify `resolved.startswith(extraction_dir)`. Abort if not. |
| No symbolic links | Check `entry.external_attr` for symlink flag. Reject any ZIP entry that is a symlink. Python: `stat.S_ISLNK(entry.external_attr >> 16)`. |
| Allowlist filenames | Expected: `conversations.json`, `user.json`, `message_feedback.json`, etc. If a filename does not match the expected set, log a warning but process only known files. |

### 4.3 File Type Validation

**Applies:** YES
**Priority:** MUST

| Control | Implementation |
|---------|---------------|
| Magic bytes validation (ZIP) | First 4 bytes must be `PK\x03\x04` (0x504B0304) or `PK\x05\x06` (empty archive). Reject anything else before attempting to open as ZIP. |
| Extension validation | Uploaded file must have `.zip` extension. |
| Content-Type validation | Accept `application/zip`, `application/x-zip-compressed`, `application/octet-stream`. Do NOT rely on Content-Type alone (can be spoofed). Magic bytes are authoritative. |
| JSON validation inside ZIP | Each extracted file must parse as valid JSON. Use `json.loads()` with a size limit on the string. Reject if parsing fails. |
| No executable content | Scan extracted filenames for `.exe`, `.bat`, `.sh`, `.py`, `.js`, `.html`, `.php`, `.dll`, `.so`. Reject if any are found. |

### 4.4 Malicious JSON Content

**Applies:** YES
**Priority:** MUST

| Control | Implementation |
|---------|---------------|
| Schema validation | Validate against expected ChatGPT export schema. Must have known top-level keys. Reject if structure does not match. |
| Depth limit | Reject JSON with nesting depth > 50 levels (protection against parser abuse). Python: use `json.loads()` which handles this, but add explicit depth check if using streaming parser. |
| String length limit | Individual string values > 1MB are suspicious. Log and truncate or reject. |
| No code execution | Never `eval()`, `exec()`, or `compile()` on any content from the uploaded file. |
| Character encoding | Enforce UTF-8. Reject files with invalid UTF-8 sequences. |
| Total JSON size limit | Max 500MB decompressed JSON. Process in streaming fashion for large files if possible. |

### 4.5 Upload Implementation Checklist

```
UPLOAD REQUEST RECEIVED
  |
  +-- [1] Check Content-Length header <= 50MB                    → 413 Payload Too Large
  +-- [2] Check Content-Type is zip-compatible                   → 415 Unsupported Media Type
  +-- [3] Read first 4 bytes, verify ZIP magic                  → 400 Bad Request
  +-- [4] Open as ZipFile, check entry count <= 50              → 400 Bad Request
  +-- [5] For each entry:
  |     +-- Check filename (no .., no /, no null, no symlink)   → 400 Bad Request
  |     +-- Check compression ratio < 100:1                     → 400 Bad Request
  |     +-- Check cumulative extracted size < 500MB             → 400 Bad Request
  |     +-- Check file extension is .json                       → skip non-JSON files
  |     +-- Extract to isolated temp directory
  +-- [6] Parse each JSON file, validate schema                 → 400 Bad Request
  +-- [7] Count conversations, check within limits              → 400 Bad Request
  +-- [8] All validations passed → begin processing
  +-- [9] On completion or failure → delete temp directory
  +-- [10] On timeout → delete temp directory
```

---

## 5. GDPR Compliance

### 5.1 Does GDPR Apply?

**YES.** Even though the service is stateless, GDPR applies because:
- We "process" personal data (Article 4(2) defines processing as "any operation ... performed on personal data" including "retrieval, consultation, use, ... structuring, ... adaptation or alteration")
- Conversation histories are personal data (they contain opinions, preferences, behavioral patterns, potentially health/financial/relationship information)
- If any user is in the EU/EEA, GDPR applies regardless of where the service is hosted
- The data likely includes "special categories" under Article 9 (political opinions, religious beliefs, health data, etc.) which triggers heightened requirements

### 5.2 Controller vs. Processor

| Role | Entity | Why |
|------|--------|-----|
| **Data Controller** | The end user uploading their own data | They determine the purpose (get their identity model) and means (using our service). They initiate the processing. |
| **Data Processor** | Base Layer (our service) | We process personal data on behalf of the user, according to their instructions (upload → process → return). |
| **Sub-Processor** | Anthropic | We send data to Anthropic's API for processing. Anthropic processes on our instructions. |

**Implications:**
- We need a **Data Processing Agreement (DPA)** with Anthropic (they offer one — sign it)
- We need a clear **Privacy Policy** informing users what happens to their data
- We need a **Terms of Service** establishing the user as controller

### 5.3 GDPR Requirements Mapped

| Requirement | Applies | Implementation | Priority |
|-------------|---------|---------------|----------|
| **Lawful basis for processing (Art. 6)** | YES | Consent: user explicitly uploads their data. Display clear consent notice before upload: "By uploading, you consent to processing your conversation data through our service and Anthropic's API to generate your identity model." | MUST |
| **Purpose limitation (Art. 5(1)(b))** | YES | State the specific purpose: "generating a behavioral identity model." Do not use data for any other purpose (analytics, training, marketing). | MUST |
| **Data minimization (Art. 5(1)(c))** | YES | Process only what is needed. If only message content is needed, discard metadata (timestamps, message IDs, model slugs) before sending to Anthropic. | SHOULD |
| **Storage limitation (Art. 5(1)(e))** | YES | Ephemeral by design. Document and enforce: uploaded data deleted within 15 minutes of job completion, or 1 hour max regardless of status. This is a GDPR strength. | MUST |
| **Integrity and confidentiality (Art. 5(1)(f))** | YES | TLS in transit, isolated processing, access controls, all covered in OWASP sections. | MUST |
| **Right to erasure (Art. 17)** | YES | Easy: data is deleted automatically. If user requests early deletion, provide an endpoint or mechanism: DELETE /job/{id} that immediately purges all associated data. | MUST |
| **Right to access (Art. 15)** | PARTIAL | The user uploaded their own data and receives the output. No additional data is retained to "access." Document this in privacy policy. | MUST (document) |
| **Right to portability (Art. 20)** | PARTIAL | The identity model IS the portable output. Provide in a standard format (Markdown, JSON). | MUST |
| **Privacy by design (Art. 25)** | YES | Ephemeral processing is privacy by design. Document architectural decisions that embed privacy: no accounts, no data retention, no logs of content, automatic deletion. | MUST |
| **Data breach notification (Art. 33/34)** | YES | Even ephemeral data can be breached during processing. Have a breach response plan. Notify supervisory authority within 72 hours. Notify affected users "without undue delay" if high risk. | SHOULD |
| **Records of processing (Art. 30)** | YES | Maintain a Record of Processing Activities (ROPA). Document: categories of data processed, purposes, sub-processors (Anthropic), retention periods, security measures. | SHOULD |
| **Transparency (Art. 13/14)** | YES | Privacy policy must state: identity of processor, purpose, legal basis, sub-processors, retention period, rights, contact for complaints. | MUST |
| **Special categories (Art. 9)** | YES | Conversation histories likely contain health, political, religious, or sexual orientation data. Explicit consent is the lawful basis. Consent notice must specifically mention this. | MUST |

### 5.4 Data Protection Impact Assessment (DPIA)

**Is one required? YES, almost certainly.**

A DPIA is required when processing is "likely to result in a high risk" to individuals. The following triggers apply to our service:

| DPIA Trigger | Applies? |
|-------------|----------|
| Systematic and extensive profiling | YES — we build behavioral models from conversation data |
| Large-scale processing of special categories | LIKELY — conversation histories contain health/political/religious data |
| New technology | ARGUABLY — AI-based behavioral modeling from conversation data is novel |
| Evaluation or scoring of individuals | YES — we score and classify behavioral patterns |

**DPIA contents (Art. 35(7)):**
1. Systematic description of processing operations and purposes
2. Assessment of necessity and proportionality
3. Assessment of risks to rights and freedoms
4. Measures to address risks (this entire document)

**Priority:** SHOULD before launch, MUST before any EU marketing or significant EU user base.

### 5.5 Cross-Border Data Transfer

| Concern | Detail | Priority |
|---------|--------|----------|
| User data → our servers | If we host in EU, no transfer issue for EU users. If US-hosted, need legal mechanism. | MUST (decide hosting) |
| Our servers → Anthropic API | Anthropic's API servers are in the US. EU personal data transferred to US requires: (1) Anthropic's DPA with Standard Contractual Clauses, or (2) EU-US Data Privacy Framework self-certification by Anthropic. Sign Anthropic's DPA which includes SCCs. | MUST |
| Transparency | Privacy policy must disclose: "Your data is processed by Anthropic's API in the United States." | MUST |

---

## 6. SOC 2 Readiness

### 6.1 Overview

SOC 2 is an auditing framework based on AICPA's Trust Services Criteria. We are NOT seeking certification for launch, but building patterns that align with eventual SOC 2 Type II.

**Why it matters:** Mem0 (direct competitor) has SOC 2 Type I and is pursuing Type II. Enterprise customers will ask.

### 6.2 Trust Services Criteria Applicability

| Criteria | Applies | Notes |
|----------|---------|-------|
| **Security (CC)** | YES — Required for all SOC 2 | Access controls, encryption, monitoring, incident response. Everything in this document. |
| **Availability (A)** | PARTIAL | Relevant if we promise uptime SLAs. Less critical for a processing service than a real-time API. |
| **Processing Integrity (PI)** | YES | Ensures processing is complete, accurate, timely. Critical for us: does the identity model accurately reflect the input data? |
| **Confidentiality (C)** | YES | Personal conversation data is confidential. Must demonstrate controls for protecting it during processing. |
| **Privacy (P)** | YES | Overlaps with GDPR. PII handling, consent, disclosure, retention, disposal. |

### 6.3 Day-1 Design Patterns for SOC 2 Alignment

| SOC 2 Control | Design Pattern | Priority |
|---------------|---------------|----------|
| **CC1.1: Control environment** | Document security policies and procedures. This document is a start. | SHOULD |
| **CC2.1: Information and communication** | Security incident response plan. Document who does what when a breach occurs. | SHOULD |
| **CC3.1: Risk assessment** | Threat model (see A04). Document risks and mitigations. | MUST |
| **CC5.1: Control activities** | Automated security controls (rate limiting, input validation, file scanning). Manual controls documented. | MUST |
| **CC6.1: Logical access controls** | Infrastructure access via SSH key/SSO only. No shared credentials. Principle of least privilege. | MUST |
| **CC6.2: Access review** | Quarterly review of who has access to production infrastructure. | SHOULD |
| **CC6.6: System boundary protection** | Firewall rules, network segmentation, WAF. | SHOULD |
| **CC7.1: Monitoring** | Logging and alerting (see A09). Anomaly detection on usage patterns. | MUST |
| **CC7.2: Incident detection** | Automated alerts for security events. Define what constitutes a security event. | SHOULD |
| **CC7.3: Incident response** | Documented incident response procedure with roles, escalation, communication plan. | SHOULD |
| **CC8.1: Change management** | All code changes via PR with review. No direct commits to main. CI/CD pipeline enforces tests. | SHOULD |
| **CC9.1: Risk mitigation** | This entire document. | MUST |
| **PI1.1: Processing completeness and accuracy** | Automated tests that verify pipeline output quality. Checksums on input/output. | SHOULD |
| **C1.1: Confidential information identification** | Classify all data types: conversation content (CONFIDENTIAL), identity model output (CONFIDENTIAL), job metadata (INTERNAL), server logs (INTERNAL). | SHOULD |
| **C1.2: Confidential information disposal** | Automated deletion with verification. Audit log proving deletion occurred. | MUST |
| **P1-P8: Privacy criteria** | Overlap with GDPR section. Privacy notice, consent, data quality, monitoring, breach response. | SHOULD |

### 6.4 What Mem0 Does (Competitive Baseline)

Based on public information from Mem0's security page:
- SOC 2 Type I certified, pursuing Type II
- HIPAA-ready
- Encryption at rest and in transit
- Zero-trust access controls
- BYOK (bring-your-own-key) encryption
- Audit logging for all memory operations
- Real-time monitoring and incident response

**Our positioning:** We cannot match Mem0's certifications at launch. But we can match or exceed their technical controls for our narrower use case (ephemeral processing vs. persistent memory storage). Our ephemeral design is inherently lower risk — Mem0 stores data permanently, we do not.

---

## 7. Dependency Security

### 7.1 Python Dependencies

| Tool | Purpose | Integration | Priority |
|------|---------|-------------|----------|
| **pip-audit** | Scans installed packages against the Python Packaging Advisory Database (PyPI). Official pypa tool by Trail of Bits/Google. | Run in CI: `pip-audit --require-hashes --strict`. Fail build on HIGH/CRITICAL. | MUST |
| **Safety** | Scans against Safety DB (broader coverage, maintained by PyUp). | Run alongside pip-audit for dual coverage: `safety check`. Free tier available. | SHOULD |
| **Bandit** | Static analysis of YOUR code for security anti-patterns (eval, exec, pickle, hardcoded passwords, etc.). | Run in CI: `bandit -r src/ -ll`. Fail on HIGH severity. | MUST |
| **pip install --require-hashes** | Verifies package integrity via hash comparison. | Generate hashes: `pip-compile --generate-hashes`. Install: `pip install --require-hashes -r requirements.txt`. | SHOULD |

### 7.2 npm / Node.js Dependencies (Frontend)

| Tool | Purpose | Integration | Priority |
|------|---------|-------------|----------|
| **npm audit** | Built-in scanning against npm advisory database. | Run in CI: `npm audit --audit-level=high`. Fail build on HIGH/CRITICAL. | MUST |
| **GitHub Dependabot** | Automated PRs for vulnerable dependencies. | Enable in `.github/dependabot.yml` for both pip and npm ecosystems. | MUST |
| **Snyk** | Comprehensive SCA with deeper transitive dependency analysis. | Free tier for open-source projects. `snyk test` in CI. | NICE |
| **Socket.dev** | Detects supply chain attacks (typosquatting, install scripts, network access). | GitHub App integration. Flags suspicious packages in PRs. | NICE |

### 7.3 Anthropic SDK Considerations

| Concern | Guidance | Priority |
|---------|----------|----------|
| **Pin version** | Pin `anthropic==X.Y.Z` in requirements. Do not use `>=` or `~=`. Test upgrades in staging before production. | MUST |
| **Review changelog on upgrade** | Check for breaking changes, security fixes, and new default behaviors. | MUST |
| **Monitor for advisories** | Watch Anthropic's GitHub repo and security page for vulnerability disclosures. | SHOULD |
| **Network behavior** | The SDK makes HTTPS calls to api.anthropic.com. Verify no unexpected outbound connections (e.g., telemetry, analytics). | SHOULD |
| **API key handling** | SDK reads key from environment variable `ANTHROPIC_API_KEY`. Verify SDK does not log or expose the key. | MUST |

### 7.4 Pinning vs. Floating Versions

| Strategy | When to use | Trade-off |
|----------|------------|-----------|
| **Exact pin** (`==1.2.3`) | Production dependencies, Anthropic SDK, any package that touches user data. | Maximum reproducibility. Must manually update. |
| **Compatible release** (`~=1.2`) | Development/testing tools (pytest, black, mypy). | Gets patch updates automatically. Minor risk of breakage. |
| **Minimum version** (`>=1.2`) | NEVER for production. | Unpredictable. A new release could break or introduce vulnerabilities. |

**Recommendation:** Pin everything in production. Use Dependabot to manage updates. Review and merge Dependabot PRs weekly.

### 7.5 Lock File Management

| File | Purpose | Commit to VCS? |
|------|---------|----------------|
| `requirements.txt` (with hashes) | Exact production dependencies with integrity verification | YES |
| `requirements-dev.txt` | Development/testing dependencies | YES |
| `package-lock.json` | Exact frontend dependencies | YES |
| `.python-version` | Python interpreter version | YES |

---

## 8. Rate Limiting and Abuse Prevention

### 8.1 Rate Limits

| Limit | Value | Enforcement Point | Priority |
|-------|-------|-------------------|----------|
| **Upload file size** | 50MB max (compressed) | Reverse proxy (nginx) + application | MUST |
| **Decompressed file size** | 500MB max | Application (during extraction) | MUST |
| **Requests per IP per minute** | 5 (upload endpoint) | Reverse proxy or application middleware | MUST |
| **Requests per IP per hour** | 10 (upload endpoint) | Application middleware with persistent counter (Redis or in-memory) | MUST |
| **Requests per IP per day** | 25 (upload endpoint) | Application middleware | MUST |
| **Concurrent jobs per IP** | 3 | Application middleware | MUST |
| **Status check rate** | 30 per minute per IP | Reverse proxy | SHOULD |
| **Download rate** | 10 per minute per IP | Reverse proxy | SHOULD |
| **Total concurrent jobs (system)** | Configurable ceiling (e.g., 50) | Application queue | MUST |
| **Request body read timeout** | 30 seconds | Reverse proxy | MUST |
| **Processing timeout** | 5 minutes per job | Application (async worker) | MUST |

### 8.2 API Cost Abuse Prevention

This is the most critical abuse vector. Each upload triggers Anthropic API calls that cost real money.

| Control | Implementation | Priority |
|---------|---------------|----------|
| **Per-job cost tracking** | Estimate token count before sending to Anthropic. Log actual token usage from response. Track cumulative cost per IP per day. | MUST |
| **Cost ceiling** | Hard cap: e.g., $50/hour, $200/day total across all jobs. When hit, return 503 Service Unavailable to new uploads. | MUST |
| **Per-IP cost ceiling** | Max estimated API cost per IP per day (e.g., equivalent to 10 large exports). Prevents single actor from consuming budget. | MUST |
| **Conversation count limit** | Max conversations per upload (e.g., 5,000). ChatGPT exports can contain thousands — cap at a reasonable number. | MUST |
| **Message count limit** | Max messages per conversation to send to API (e.g., 200). Truncate older messages. | SHOULD |
| **Pre-flight cost estimate** | Before processing, estimate API cost. If above threshold, require additional confirmation or reject. | SHOULD |
| **Kill switch** | Manual or automated ability to disable uploads instantly. Environment variable or API flag. | MUST |

### 8.3 Abuse Detection Patterns

| Pattern | Indicator | Response |
|---------|-----------|----------|
| **Credit drain** | Multiple large uploads from same IP in short period | Rate limit, then temporary ban (1 hour) |
| **Bot activity** | Identical file sizes, missing headers, no referrer, scripted User-Agent | CAPTCHA challenge or block |
| **Content abuse** | Uploading non-ChatGPT files (wrong JSON schema) repeatedly | Increment failed-upload counter; temporary ban after 5 failures |
| **Enumeration** | Sequential status/download requests with different IDs | Rate limit, log, alert |
| **Distributed attack** | Same file from many IPs (fingerprint by file hash) | Dedup by file hash; limit processing of identical files |

### 8.4 Response Headers for Rate Limiting

Include these in all rate-limited responses:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1677721600
Retry-After: 3600  (on 429 responses)
```

Return `429 Too Many Requests` with a JSON body explaining the limit hit and retry time.

---

## 9. Implementation Priority Matrix

### MUST for Launch (Before Any Public User)

| # | Item | Section | Effort |
|---|------|---------|--------|
| 1 | TLS everywhere (HTTPS only, HSTS) | A02, Headers | LOW |
| 2 | All security headers configured | Headers | LOW |
| 3 | ZIP bomb protection (size, ratio, count limits) | File Upload | MEDIUM |
| 4 | Path traversal prevention (filename sanitization) | File Upload | MEDIUM |
| 5 | Symlink rejection in ZIP | File Upload | LOW |
| 6 | Magic bytes validation | File Upload | LOW |
| 7 | JSON schema validation | A03, File Upload | MEDIUM |
| 8 | Unguessable job IDs (UUIDv4 / secrets.token_urlsafe) | A01, API1 | LOW |
| 9 | Time-limited download URLs (15 min TTL) | A01, API1 | LOW |
| 10 | Automatic data deletion after job completion | A01, GDPR | MEDIUM |
| 11 | Rate limiting on upload endpoint | API4, Abuse | MEDIUM |
| 12 | Per-IP concurrent job limit | API4, Abuse | LOW |
| 13 | Anthropic API cost ceiling (daily hard cap) | A04, Abuse | MEDIUM |
| 14 | Kill switch for uploads | A04, Abuse | LOW |
| 15 | No PII in logs | A09 | MEDIUM |
| 16 | Production config hardened (no debug, no stack traces) | A05 | LOW |
| 17 | Anthropic API key in environment variable only | A05, A07 | LOW |
| 18 | pip-audit in CI (fail on HIGH/CRITICAL) | A06 | LOW |
| 19 | npm audit in CI (fail on HIGH/CRITICAL) | A06 | LOW |
| 20 | Privacy policy (what data, what happens, who processes, how long) | GDPR | MEDIUM |
| 21 | Consent notice before upload (including special categories) | GDPR | LOW |
| 22 | Anthropic DPA signed | GDPR | LOW |
| 23 | CORS locked to frontend origin | A01, A05 | LOW |
| 24 | No shell commands with user data | A03 | LOW |
| 25 | Explicit response schemas (no internal field leakage) | API3 | LOW |
| 26 | Validate Anthropic API responses before processing | API10 | LOW |
| 27 | Structured audit log (job lifecycle without content) | A09, SOC2 | MEDIUM |
| 28 | Ephemeral deletion verification test | A04, GDPR | MEDIUM |

### SHOULD Before Scale (Before Marketing / Significant Traffic)

| # | Item | Section | Effort |
|---|------|---------|--------|
| 29 | DPIA completed | GDPR | HIGH |
| 30 | Breach response plan documented | GDPR, SOC2 | MEDIUM |
| 31 | CAPTCHA or proof-of-work on upload | API6, Abuse | MEDIUM |
| 32 | Sliding-window rate limiting (not just fixed window) | API8, Abuse | MEDIUM |
| 33 | Abuse detection (bot patterns, file hash dedup) | Abuse | MEDIUM |
| 34 | Alerting on anomalous usage | A09, SOC2 | MEDIUM |
| 35 | Per-job cost tracking and per-IP cost ceiling | Abuse | MEDIUM |
| 36 | Pin all dependencies with hashes | A08, Deps | LOW |
| 37 | Dependabot enabled for Python + npm | A06, Deps | LOW |
| 38 | CI/CD hardening (pinned actions, least-privilege tokens) | A08, SOC2 | MEDIUM |
| 39 | Network segmentation (egress allowlist to Anthropic only) | A10, SOC2 | MEDIUM |
| 40 | Record of Processing Activities (ROPA) | GDPR | MEDIUM |
| 41 | Incident response procedure | SOC2 | MEDIUM |
| 42 | Change management (PRs required, no direct commits) | SOC2 | LOW |
| 43 | Data minimization (strip unnecessary fields before API call) | GDPR | LOW |
| 44 | Bandit static analysis in CI | Deps | LOW |
| 45 | Safety scan alongside pip-audit | Deps | LOW |
| 46 | DELETE /job/{id} endpoint for user-initiated erasure | GDPR | LOW |
| 47 | Encrypt temp files if processing exceeds 5 minutes | A02 | MEDIUM |
| 48 | Subresource Integrity for CDN assets | A08 | LOW |

### NICE for Maturity (Enterprise Readiness / SOC 2 Pursuit)

| # | Item | Section | Effort |
|---|------|---------|--------|
| 49 | SOC 2 Type I certification | SOC2 | HIGH |
| 50 | Formal security policies and procedures | SOC2 | HIGH |
| 51 | Quarterly access reviews | SOC2 | LOW (ongoing) |
| 52 | Snyk / Socket.dev integration | Deps | LOW |
| 53 | WAF (Cloudflare, AWS WAF) | API8 | MEDIUM |
| 54 | Certificate pinning for Anthropic API | A02 | LOW |
| 55 | Bug bounty program | General | MEDIUM |
| 56 | Penetration testing (annual) | General | HIGH |
| 57 | BYOK encryption option | SOC2 (Mem0 parity) | HIGH |
| 58 | Optional user accounts with OAuth2/OIDC | A07 | HIGH |
| 59 | Processing integrity verification (input hash → output hash) | SOC2 PI | MEDIUM |
| 60 | ISO 27001 alignment | General | HIGH |

---

## Appendix A: Recommended Python Libraries

| Library | Purpose | Notes |
|---------|---------|-------|
| `safezip` | Hardened ZIP extraction | Defends against ZipSlip, ZIP bombs, malformed archives. Zero dependencies. |
| `python-magic` | File type detection via magic bytes | Wrapper around libmagic. More reliable than extension checking. |
| `jsonschema` | JSON Schema validation | Validate ChatGPT export structure before processing. |
| `pydantic` | Response schema enforcement | Ensures API responses contain only intended fields. |
| `slowapi` | Rate limiting for FastAPI | Built on `limits` library. Redis or in-memory backend. |
| `pip-audit` | Dependency vulnerability scanning | Official pypa tool. CI integration. |
| `bandit` | Python static security analysis | Finds eval/exec/pickle/hardcoded secrets in your code. |
| `structlog` | Structured logging | JSON logs with consistent fields. Easy to avoid PII leakage. |

## Appendix B: Compliance Evidence Checklist

For each control, maintain evidence of implementation:

| Evidence Type | Examples |
|--------------|---------|
| **Configuration** | Security header values, rate limit values, CORS config |
| **Code** | Input validation functions, file sanitization logic, deletion routines |
| **Tests** | Automated tests that verify: ZIP bomb rejection, path traversal rejection, rate limit enforcement, data deletion, no PII in logs |
| **Logs** | Audit logs showing job lifecycle, deletion events, rate limit triggers |
| **Documentation** | This document, privacy policy, threat model, DPIA, incident response plan |
| **Third-party** | Anthropic DPA, dependency audit reports, CI/CD pipeline config |

## Appendix C: Key Reference URLs

- OWASP Top 10 (2021): https://owasp.org/Top10/2021/
- OWASP API Security Top 10 (2023): https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- GDPR Article 28 (Processor): https://gdpr-info.eu/art-28-gdpr/
- GDPR Article 35 (DPIA): https://gdpr-info.eu/art-35-gdpr/
- Anthropic Privacy Center: https://privacy.claude.com/
- Anthropic DPA: https://privacy.claude.com/en/articles/7996862-how-do-i-view-and-sign-your-data-processing-addendum-dpa
- SOC 2 Trust Services Criteria: https://secureframe.com/hub/soc-2/trust-services-criteria
- Mem0 Security: https://mem0.ai/security
- pip-audit: https://pypi.org/project/pip-audit/
- safezip: https://github.com/barseghyanartur/safezip
- Snyk Zip Slip: https://security.snyk.io/research/zip-slip-vulnerability
- MDN Security Headers: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP

---

**Document version:** 1.0
**Created:** 2026-03-01
**Scope:** Base Layer web file processing service
**Review cadence:** Before each major release and quarterly thereafter
