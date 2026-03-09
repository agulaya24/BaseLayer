# Security & Code Audit — Session 55

**Date:** 2026-02-28
**Scope:** Full codebase security review + code quality audit

---

## Security Audit Summary

**Overall risk profile: LOW** (local-first architecture, stdio MCP, no network exposure)

### Positive Findings (6)
- API keys loaded from environment variables only — no hardcoded keys
- All major SQL paths use parameterized queries (`?` binding)
- ZipSlip protection in ZIP import (`import_conversations.py:462-473`)
- MCP server uses stdio transport — no network socket
- `.gitignore` covers all sensitive data (database, vectors, identity layers, entity map, .env)
- Privacy tests (`test_privacy.py`) explicitly verify no key leakage

### Issues by Severity

| Severity | Count | Key Issues |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 1 | Hardcoded personal anchors in committed `store_anchors.py` |
| MEDIUM | 4 | MEMORY_SYSTEM_ROOT not validated, prompt injection in extraction, MCP identity layer injection chain, CLAUDE.md personal details in repo |
| LOW | 13 | f-string LIMIT clauses, default file permissions, LIKE wildcards, dependency pinning, logging, etc. |

### Action Items

**Must fix before release:**
1. `store_anchors.py:49-140` — Move hardcoded user-specific axioms out of committed code into data/ (gitignored)
2. `CLAUDE.md` — Split into public (generic instructions) and private (session history) versions

**Should fix:**
3. `extract_facts.py` extraction prompts — Add XML delimiters around conversation content to reduce prompt injection surface
4. `config.py:29-34` — Validate `MEMORY_SYSTEM_ROOT` exists and is a directory before using
5. `mcp_server.py:220` — Escape LIKE metacharacters in search_facts
6. Database files — Set restrictive permissions (0o600) on creation

---

## Code Quality Audit Summary

**20 issues found** (4 CRITICAL, 4 HIGH, 4 MEDIUM, 8 LOW)

### CRITICAL (must fix pre-release)

| # | Issue | File | Line |
|---|---|---|---|
| 1 | `len(messages) < 2` blocks single-message extraction | extract_facts.py | 1318 |
| 2 | Hardcoded user-specific axioms | store_anchors.py | 49-140 |
| 3 | Hardcoded user-specific inter-axiom conflicts | author_layers.py | 601-638 |
| 4 | Hardcoded user-specific cluster descriptions | assemble_brief.py | 79-180+ |

### HIGH (should fix)

| # | Issue | File(s) | Impact |
|---|---|---|---|
| 5 | Duplicate embedding model init (12 scripts) | Multiple | Memory bloat, inconsistent state |
| 6 | Bare `except Exception` without logging | extract_facts.py, author_layers.py | Silent failures |
| 7 | Shared Anthropic client creation not centralized | Multiple (14+ locations) | `llm_provider.py` exists but unused |
| 8 | No timeout/retry on API calls | author_layers.py, consolidate_enrichments.py | Long jobs fail with no recovery |

### MEDIUM

| # | Issue | File(s) |
|---|---|---|
| 9 | Entity map lacks gender field | entity_map.json |
| 10 | MIN_MESSAGES_FOR_EXTRACTION vs len<2 conflict | config.py:175, extract_facts.py:1318 |
| 11 | Weak heuristic for user anchor detection | author_layers.py:630-635 |
| 12 | No centralized Anthropic client management | Multiple |

### LOW (8 items)
Bare `pass` without comments, User-specific test data, pronoun default he/him in prompts, inconsistent connection closure, arbitrary 20-fact extraction cap, no centralized logging, no connection pool, relative imports in cli.py.

---

## Recommended Fix Priority

### Phase 1: Pre-Release (Must)
1. Remove all hardcoded user-specific content from committed code (store_anchors.py, author_layers.py, assemble_brief.py)
2. Fix `len(messages) < 2` to support single-message sources
3. Split CLAUDE.md into public/private versions
4. Add XML delimiters in extraction prompts

### Phase 2: Code Quality (Should)
5. Centralize embedding model initialization
6. Route all API calls through `llm_provider.py`
7. Add timeout/retry to author_layers.py and consolidate_enrichments.py
8. Add logging to all exception handlers
9. Add gender field to entity_map.json
10. Add they/them pronoun fallback in layer generation prompts

### Phase 3: Hardening (Nice to Have)
11. Set restrictive file permissions on database/vector/layer files
12. Pin dependency version ranges in pyproject.toml
13. Validate MEMORY_SYSTEM_ROOT environment variable
14. Escape LIKE wildcards in MCP search
15. Centralize logging configuration
