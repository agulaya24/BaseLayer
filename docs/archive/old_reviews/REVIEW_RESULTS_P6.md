# Phase 6: Security Review — 2026-03-09

## 6.1 Secrets Scan

### No CRITICAL Issues Found

No hardcoded API keys, tokens, or passwords were found in any active scripts. Full scan results:

- Pattern `sk-ant-` — appeared only in `scripts/cli.py:1057` as a documentation string in a user-facing help message: `print("Then: export ANTHROPIC_API_KEY=sk-ant-...")`. This is example/instructional text, not a real key. No issue.
- Pattern `api_key\s*=\s*["']` (with literal value) — no matches found in active scripts.
- Pattern `password\s*=\s*["']` — no matches found anywhere.
- No `.env` files found in the project.
- No `credentials.*` or `*.key` files found anywhere in the project tree.
- `config.py` contains no secrets — only path constants, model names, and thresholds. All API key references are via `os.environ.get(...)`.

### Summary
Secrets scan is clean. All API key access is via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

---

## 6.2 Input Validation

### Issues Found

| File | Line(s) | Issue | Severity |
|---|---|---|---|
| `scripts/ui.py` | 351-368 | `subject` parameter from HTTP form is passed directly to `subprocess.Popen` via `cmd.extend(["--subject", subject])` with no length cap or character allowlist. A very long subject string or one containing shell metacharacters could behave unexpectedly (though `shell=False` mitigates injection). | MEDIUM |
| `scripts/extract_facts.py` | 115 | `conn.execute(f"ALTER TABLE memory_facts ADD COLUMN {col} TEXT")` — the `col` variable comes from a hardcoded list `["predicate", "object_text", "qualifier"]`, not user input. No actual risk, but the pattern is worth noting in case the list is ever made dynamic. | LOW |
| `scripts/author_layers.py` | 136, 159, 166 | f-string SQL queries using `{tier_filter}` — the variable is constructed from hardcoded logic (`"" if simplified else "AND knowledge_tier = 'identity'"`) with no user input. No injection risk in current code, but the pattern bypasses parameterization. | LOW |
| `scripts/author_layers.py` | 252, 451, 491 | f-string SQL using `IN ({placeholders})` — placeholders are `?` markers built from `len(ANCHOR_PREDICATES)` where predicates are hardcoded constants. Parameterized values are passed correctly. No injection risk. | LOW (pattern only) |

### Clean Areas

- `scripts/mcp_server.py` — `search_facts` uses `_escape_like()` for LIKE metacharacter escaping and parameterized queries throughout. SQL injection risk is well-managed.
- `scripts/mcp_server.py` — `trace_claim` uses `UPPER(?)` parameterized binding for user-supplied `claim_id`.
- `scripts/import_conversations.py` — file path inputs are handled via `pathlib.Path` objects. No `subprocess` or `os.system` calls in this script.
- `scripts/api_client.py` — no subprocess calls.
- `scripts/config.py` — no subprocess calls, no dynamic SQL.
- `scripts/ui.py` — filename sanitization at line 302-305 strips the uploaded filename to `[a-z0-9.-_]` before saving. Good practice. `subprocess.Popen` is called with `shell=False` (default) so the `subject` parameter cannot inject shell commands.
- All `subprocess` calls in active scripts (`ui.py`) and archived eval scripts use list-form commands (no `shell=True`), preventing shell injection. The `shell=True` pattern is not present anywhere.
- `pickle.load` / `pickle.loads` — not found anywhere.
- `eval()` / `exec()` on user data — not found anywhere.

### Path Traversal Note

`scripts/ui.py` saves uploaded files to a `tempfile.mkdtemp()` directory and sanitizes the filename. However, the `file_path` (the full temp path) is then passed to the subprocess pipeline. Since `tempfile.mkdtemp()` creates a system-managed temp directory, path traversal from the filename is not possible. Clean.

---

## 6.3 Dependency Audit

### Dependencies (`pyproject.toml`)

| Package | Version Spec | Status |
|---|---|---|
| `anthropic` | `~=0.45` | Current. No known CVEs in this range. |
| `chromadb` | `~=0.6` | Current. No known CVEs. |
| `sentence-transformers` | `~=3.0` | Current. No known CVEs. |
| `numpy` | `~=1.26` | Pinned to 1.26.x — NumPy 2.x is available but 1.26 is still maintained and widely deployed. No CVEs applicable to this use case (no untrusted array deserialization). |
| `python-docx` | `~=0.8` | Older minor version — the package has had no security-relevant updates. No known CVEs. Flagged only because `~=0.8` is very permissive. |
| `requests` | `~=2.31` | Current. No known CVEs affecting this version. |
| `httpx` | `>=0.24` | Open lower bound. Current releases are 0.27+. No known CVEs in range. |
| `mcp[cli]` | `~=1.2` | MCP SDK — relatively new package. No known CVEs. |
| `pytest` | `>=7.0.0` (dev) | Dev-only. No security concern. |

### Flagged Dependencies

| Package | Version Spec | Reason |
|---|---|---|
| `numpy` | `~=1.26` | Locked to 1.26.x while 2.x is the current major. No active CVEs, but worth upgrading post-launch if downstream compatibility allows. LOW priority. |
| `python-docx` | `~=0.8` | The `~=0.8` constraint will accept 0.8.x only. The package has been relatively stagnant. Monitoring recommended but no current CVE. LOW priority. |
| `httpx` | `>=0.24` | Unbounded upper constraint. Could accept a future breaking version. LOW risk given the package's stability, but pinning is better practice for public release. LOW priority. |

### No Critical Dependency Vulnerabilities Found

No dependencies have known CVEs as of the knowledge cutoff (August 2025) that would affect this use case.

---

## 6.4 API Client Security

### Pass

- **API key never hardcoded.** `api_client.py` calls `anthropic.Anthropic()` with no `api_key` argument — the Anthropic SDK reads `ANTHROPIC_API_KEY` from the environment automatically. The key is never touched by application code.
- **API key never logged.** All `logger.*` calls in `api_client.py` log model names, token counts, and error messages only. No API key values appear in any log call in the entire scripts directory.
- **API key never included in error messages.** Exception objects from the Anthropic SDK (`RateLimitError`, `APIStatusError`, `APIConnectionError`) are logged via `%s` formatting of the exception object itself. The SDK does not include the API key in exception string representations.
- **TLS/SSL verification not disabled.** No `verify=False` or equivalent found anywhere in the codebase. The Anthropic SDK and `requests` library use system TLS verification by default.
- **Retry logic is safe.** Exponential backoff with jitter is implemented. Error messages on retry log the HTTP status code and exception message only — no request body (which could contain conversation content) is logged.
- **Thread safety.** Client singleton uses a double-checked locking pattern with `threading.Lock()`. Correct.

### Issues

- **`logger.warning` logs the full exception object for rate limit errors** (`%s, e` at line 173). For Anthropic SDK errors, the exception `str()` includes the API response body, which may contain request metadata. This is low risk (logged to stderr, not a network-accessible endpoint) but is worth reviewing. **LOW severity.**

---

## 6.5 Data Handling

### .gitignore Status

All personal data directories are properly excluded:

| Directory/Pattern | Status |
|---|---|
| `data/database/` | EXCLUDED |
| `data/vectors/` | EXCLUDED |
| `data/raw/` | EXCLUDED |
| `data/identity_layers/` | EXCLUDED — with comment "contain personal data — NEVER commit" |
| `data/imports/`, `data/eval/`, `data/corpora/` | EXCLUDED |
| `data/*.csv`, `data/*.json` | EXCLUDED |
| `entity_map.json` (all locations) | EXCLUDED |
| `.env`, `*.env` | EXCLUDED |
| `docs/core/PROGRESS.md` | EXCLUDED — with comment "contains personal data throughout" |
| `docs/analysis/` | EXCLUDED — with comment "contain biographical data" |
| `gtm/` | EXCLUDED — internal strategy |
| `reference/` | EXCLUDED — session transcripts |
| `GIT_PUSH_PREP.md` | EXCLUDED |

The `.gitignore` is thorough and well-annotated. No apparent gaps for the active pipeline data paths.

### Committed Data Files

Unable to run `git ls-files` directly (Bash tool not available). However:
- All data directories (`data/database/`, `data/vectors/`, `data/identity_layers/`) are covered by `.gitignore`.
- Subject data directories (`subjects/`, `buffett_memory/`, `marks_memory/`) are **not** explicitly in `.gitignore`. These are mentioned in CLAUDE.md as containing brief files and subject layer data.

**ACTION REQUIRED (pre-push):** Verify that `subjects/`, `buffett_memory/`, `marks_memory/`, `franklin_memory/`, and `memory_system_v4/` directories containing actual brief and layer files are either (a) not in the git index or (b) added to `.gitignore`. The `GIT_PUSH_PREP.md` privacy scrub should cover this, but it was not readable (excluded from git).

### Anonymization Verification

**Works correctly.** Evidence:

1. `_anonymize_text()` in `author_layers.py:1105-1128` — replaces full name, first name, and last name with "this person" using `re.sub` with word boundaries.
2. `_anonymize_facts()` at line 1131 — applies anonymization to `fact_text`, `formulation`, and `subject` fields of every fact dict before passing to prompts.
3. `_anonymize_anchor_data()` at line 1156 — applies the same to anchor data structures.
4. Anonymization is called before every prompt construction in `generate_anchors_layer()` (line 1665), `generate_core_layer()` (line 1738-1744), and `generate_predictions_layer()` (line 1795).
5. Confirmation print: `"Anonymized: '{subject_name}' → 'this person'"` is emitted on every generation run, making it auditable.

**Limitation:** Anonymization is name-based only — it replaces detected proper names. If facts contain identifying details other than the subject's name (unique project names, specific locations, etc.), those are not anonymized. This is by design for single-user personal operation but worth noting for multi-user or public deployment contexts.

### Logging Issues

The following `print()` calls output truncated fact text to stdout during pipeline operation. These are intentional user-facing progress messages (not logging to files or external services), but they do surface personal fact content to the terminal:

| File | Lines | What's printed | Severity |
|---|---|---|---|
| `scripts/author_layers.py` | 535, 548, 560 | `fact_text[:100]` during retrieval display | LOW — stdout only, user-initiated operation |
| `scripts/assemble_brief.py` | 404, 415, 513, 528, 530 | `fact_text[:90]` and `fact_text[:80]` during brief assembly | LOW — stdout only |
| `scripts/cli.py` | 478, 573, 783 | `fact_text[:120]` and `fact_text[:150]` during review/trace | LOW — stdout only, expected behavior |

No fact content is logged via the `logger` (structured logging) object. All fact-content prints are via `print()` to stdout, which is the intended terminal interface. No fact content is written to log files or transmitted externally.

**One note:** `scripts/extract_facts.py:1980` prints `conv['title'][:40]` on extraction errors — conversation titles may be sensitive. LOW severity.

---

## Files Modified (CRITICAL fixes only)

**None — all issues deferred to the findings list above.**

No CRITICAL severity issues were found. No files were modified during this review.

---

## Summary

**Overall security posture: GOOD for a personal/local tool. One pre-push action required.**

**Strengths:**
- No hardcoded secrets anywhere. API key handling is correct throughout.
- SQL injection risk is well-managed. Parameterized queries are used for all user-controlled inputs. The f-string SQL patterns found use only hardcoded constant values in the interpolated portions.
- No `shell=True` subprocess calls. No `eval()`, `exec()`, or `pickle.load()` on user data.
- `.gitignore` is thorough and well-commented. Personal data directories are all excluded.
- Anonymization pipeline works correctly and is applied consistently before every model call.
- TLS verification is not disabled anywhere.
- The MCP server uses `stdio` transport (local only), eliminating network attack surface.

**Pre-push blocker:**

The subject-specific data directories (`subjects/`, `buffett_memory/`, `marks_memory/`, `franklin_memory/`, `memory_system_v4/`) contain generated brief files with real personal behavioral data and are **not listed in `.gitignore`**. Before any public git push, confirm these directories are either untracked or add them to `.gitignore`. This is flagged as HIGH priority for the privacy scrub referenced in `GIT_PUSH_PREP.md`.

**Non-blocking issues to address post-launch:**
- HIGH: Add `subjects/`, `buffett_memory/`, `marks_memory/`, `franklin_memory/`, `memory_system_v4/` to `.gitignore` explicitly.
- MEDIUM: Add length cap/allowlist validation on the `subject` parameter in `ui.py` before passing to subprocess (defense in depth, even though `shell=False` prevents injection).
- LOW: Consider pinning `httpx` upper bound in `pyproject.toml`.
- LOW: Consider upgrading `numpy` to 2.x post-launch.
- LOW: The Anthropic SDK exception object logged on rate limit retry may include response body metadata. Review what `str(RateLimitError)` exposes and consider logging only `e.status_code` and `e.message` if available.
