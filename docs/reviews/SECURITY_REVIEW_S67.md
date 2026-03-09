# Security Review — Session 67 (Pre-Public Push)

**Date:** 2026-03-04
**Scope:** Comprehensive security, PII, and privacy review of `memory_system\` in preparation for pushing to a public GitHub repository.
**Prior review:** `SECURITY_CODE_AUDIT_S55.md` (2026-02-28) — referenced where applicable.
**Methodology:** Systematic grep/glob/read across all files. Bash access was denied during review, so `git ls-files` and `git log` could not be verified. **Git history audit must be performed manually before push.**

---

## Executive Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 5 | PII in committed files, personal data in pyproject.toml, entity_map.json, databases on disk, git history unverified |
| **HIGH** | 8 | Eval prompts with personal biographical details, test cases with personal data, GTM docs with full name/bio, docs with personal data, hardcoded Windows paths in docs |
| **MEDIUM** | 5 | SQL f-string patterns (safe but fragile), `__import__` usage, dependency pinning, PROGRESS.md gitignore only |
| **LOW** | 4 | Placeholder API keys in docs (acceptable), LIKE escaping already fixed, test method name references "aarik" |

**Verdict: NOT safe to push as-is.** Multiple files contain personal data that would be publicly visible. The .gitignore is comprehensive but several tracked docs and scripts contain PII.

---

## 1. SECRETS & API KEYS

### Status: CLEAN (no real secrets found)

All API key references are placeholder/documentation patterns:
- `sk-ant-...` appears in README, AGENT.md, FLOW_GUIDE.md, cli.py, MULTI_PROVIDER_PLAN.md, WEB_SERVICE_SECURITY_THREAT_MODEL.md — all as examples or instructions
- `sk-ant-test123` appears in `tests/test_cli.py` — mock test value, acceptable
- No real API keys found anywhere in the codebase
- No `.env` files found
- `test_privacy.py` explicitly tests for key leakage — good

**No action needed.**

---

## 2. PERSONAL DATA / PII

### CRITICAL — pyproject.toml author field

**File:** `memory_system\pyproject.toml` (line 13)
```
authors = [
    {name = "the developer"},
]
```

**Decision required:** If the developer wants to be publicly credited as the author, this is fine. If anonymity is desired, change to a project name or pseudonym. The CLAUDE.md mentions "Privacy scrub pending... pyproject.toml author field" — confirming this was already flagged.

### CRITICAL — entity_map.json on disk (gitignored BUT verify)

**File:** `memory_system\data\entity_map.json`
Contains: spouse name (User C), pet name (Walnut), companies (SAFA, Maxnerva), colleague name (Razvan), user name mapping.

The .gitignore covers `entity_map.json`, `scripts/entity_map.json`, and `data/entity_map.json`. **However, without `git ls-files` access, I cannot verify this file was never committed in git history.** If it was ever committed, it persists in history.

### CRITICAL — Databases and vectors on disk (gitignored BUT verify)

Found on disk:
- `data/database/memory.db` — full personal fact database
- `data/vectors/chroma.sqlite3` — vector embeddings
- `backups/2026-02-04-session4/memory.db` (and 4 other backup copies)
- `data/raw/media/` — 80+ personal images from ChatGPT exports (including a user-specific directory `user-xoaOnnYiAkRHTRoWSNvCdSDD/`)

The .gitignore covers `data/database/`, `data/vectors/`, `data/raw/`, and `backups/`. These should not be committed. **Must verify with `git ls-files` that none were ever tracked.**

### CRITICAL — LICENSE contains full name

**File:** `memory_system\LICENSE` (line 178)
```
Copyright 2026 the developer
```

**Decision required:** Standard for open source. Only flag if anonymity is desired.

### CRITICAL — Git history unverified

Without bash access to run `git log --all --diff-filter=A -- "*.db" "*.sqlite*" ".env*" "entity_map.json"`, I cannot confirm no sensitive files were ever committed. **The CLAUDE.md says "Fresh repo planned (L4 DECIDED). Same name baselayer."** If you are creating a fresh repo (not pushing this existing .git), this risk is eliminated. **Strongly recommend the fresh repo approach.**

---

## 3. HIGH SEVERITY ISSUES

### H1 — Eval prompts contain personal biographical details

**Files:**
- `scripts/run_validation_study.py` (lines 76-140, 233-280)
- `scripts/run_eval.py` (lines 61-122)

These eval prompts are written from the developer's perspective with biographical details:

| Prompt | Personal Detail |
|--------|----------------|
| P2 | "CRO roles at Series B companies" — specific career interest |
| P3 | "My partner wants to move... gym, trading setup" — relationship detail |
| P6 | "31-year-old day trader who talks to AI about his feelings" — age, occupation |
| P8 | "tweaked my back deadlifting" — physical detail |
| P9 | "pathological about building a system so AI understands you" — self-reference |
| P10 | "keep trading and building Base Layer, take a CRO role... find a cofounder" — specific career paths |
| MT-3 | "AI memory system, content business, trading, family time" — exact project list |

**These are in committed `.py` files, not gitignored.** While none contain the user's name, a motivated reader could triangulate identity from: 31-year-old + day trader + AI memory system builder + former startup founder + considering CRO roles.

**Recommendation:** Generalize eval prompts before push. Replace biographical specifics with generic alternatives ("my startup" instead of "Base Layer", remove age, etc.), or move them to a gitignored data file.

### H2 — assemble_brief.py TEST_CASES contain personal correction guards

**File:** `scripts/assemble_brief.py` (lines 1556-1599)

```python
TEST_CASES = [
    ("Tell me about my trading", ["trading", "options", "SPY"], ["canadian"]),
    ("What's my approach to risk management?", ["risk", "defined"], ["eczema"]),
    ("What games do I play?", ["Deadlock", "game"], []),
    ("Tell me about myself", [], ["canadian citizen", "eczema", "s2000", "iron condor"]),
]
```

The "should_NOT_contain" keywords reveal personal facts about the user: was incorrectly tagged as Canadian citizen, partner has eczema, does NOT own an S2000, specific trading strategy (iron condor). Also reveals specific gaming preferences (Deadlock) and trading instruments (SPY, options).

**Recommendation:** Generalize or remove these test cases before push. Replace with generic examples.

### H3 — archive/_check_status.py contains personal correction terms

**File:** `scripts/archive/_check_status.py` (line 43)
```python
for term in ["Canadian citizen", "eczema", "S2000", "iron condor"]:
```

Same personal data as H2. This is in an `archive/` subdirectory but not gitignored.

**Recommendation:** Delete or generalize.

### H4 — GTM docs contain full name and biographical details

**Files (NOT fully gitignored):**
- `gtm/content/BASE_LAYER_OVERVIEW.md` — "the developer. Former founder and CEO (Techstars '22). Built and shipped an aerospace operations platform to NASA."
- `gtm/content/SLIDE_DECK.md` — "the developer — Solo Founder"
- `gtm/content/HN_SHOW_HN_DRAFT.md` — references "the developer"
- `gtm/content/LANDING_PAGE_COPY.md` — contains `baselayer-website\`
- `gtm/strategy/GTM_STRATEGY.md` — "the developer" mentioned 5+ times, `[local path]\` paths
- `gtm/strategy/FEATURE_LIST.md` — "User B" full name
- `gtm/research/HN_LAUNCH_RESEARCH.md` — GitHub URL `baselayer`
- `gtm/outreach/LESSWRONG_POST_DRAFT.md` — personal references
- `gtm/research/USE_CASES_DEMOS_BATTLE_TESTS.md` — "User B", "User B's"

**Only these gtm subdirectories are gitignored:** `gtm/archive/generated/`, `gtm/archive/outreach/`, `gtm/archive/completed/`, `gtm/research/BAVANI_CASE_STUDY*.md`

**The rest of gtm/ is NOT gitignored and contains personal data.**

**Recommendation:** Either gitignore the entire `gtm/` directory, or scrub all personal references. The GTM directory contains marketing/strategy content that is useful internally but should not be in a public repo.

### H5 — docs/ files with personal data

**Files (NOT gitignored):**
- `docs/core/PROJECT_OVERVIEW.md` — "the developer" (eval reference), GitHub URL `baselayer`
- `docs/core/DECISIONS.md` — "Canadian citizen, eczema, S2000, Razvan" (lines 550, 1212)
- `docs/core/ARCHITECTURE.md` — "AARIK-ANALYSIS.md" reference (line 1062)
- `docs/eval/BCB_FRAMEWORK.md` — "the developer" in data table (line 35)
- `docs/eval/EVAL_FRAMEWORK.md` — "User C" named (lines 956, 965)
- `docs/eval/TRUE_BLIND_EVAL_FRAMEWORK.md` — "AARIK-SPECIFIC" heading (line 529)
- `docs/eval/CROSS_PROVIDER_IDENTITY_EVAL.md` — "the developer" named (line 39)
- `docs/reviews/CONTAMINATION_REVIEW.md` — "the developer" throughout (~15 occurrences), "User C"
- `docs/reviews/README_REVIEW_S57.md` — "the developer" multiple times, `[local path]/` path
- `docs/reviews/SECURITY_CODE_AUDIT_S55.md` — "the developer" in issue descriptions
- `docs/plans/MULTI_PROVIDER_PLAN.md` — "the developer" (lines 162, 787, 873)
- `docs/plans/WEB_SERVICE_SECURITY_THREAT_MODEL.md` — "the developer, Houston" reference
- `docs/plans/PROVENANCE_TRACE_ARCHITECTURE.md` — "the developer" reference
- `docs/plans/PIPELINE_UPGRADES_POST_FRANKLIN.md` — "the developer" in 4+ locations
- `docs/plans/EXTRACTION_CAP_SCALING_REVIEW.md` — "the developer", "User C"
- `docs/plans/TEMPORAL_RECURRENCE_DEDUP_PLAN.md` — "the developer" reference
- `docs/research/VOICE_RESEARCH.md` — "the developer" in examples (lines 228, 236)

**Note:** `docs/core/PROGRESS.md` IS gitignored. `docs/analysis/` IS gitignored. `docs/versions/` IS gitignored.

**Recommendation:** All of these docs files need an anonymization pass — replace "the developer" with "User A" or "the builder", replace "User C" with "Subject B" or "User C", replace "User B" with "User B", remove hardcoded Windows paths. Alternatively, gitignore the entire `docs/` directory and publish only code + README.

### H6 — test_contradiction.py and test_contradiction_detection.py

**Files:**
- `scripts/test_contradiction.py` (line 119): `"Jordan has eczema-related dry skin"` — references real relationship detail
- `scripts/test_contradiction_detection.py` (line 209): `"Alex founded TechCo, which was accepted into Techstars"` — parallels real biography

While these use pseudonyms ("Jordan", "Alex", "TechCo"), the specific scenarios map closely to real biographical facts. The eczema/skin reference is a known the developer correction (spouse's condition incorrectly attributed to him).

**Recommendation:** Change to fully generic scenarios that don't parallel real facts.

### H7 — run_validation_study.py multi-turn scenarios

**File:** `scripts/run_validation_study.py` (lines 233-280)

Multi-turn scenarios contain highly specific personal context: "AI memory system, content business, trading, family time", "CRO role", "cofounder for Base Layer". Even though no name is attached, these are unique enough to identify the author.

**Recommendation:** Generalize multi-turn scenarios to remove Base Layer references and specific career details.

### H8 — Hardcoded Windows paths in documentation

**Files:**
- `gtm/content/LANDING_PAGE_COPY.md` — `baselayer-website\`
- `gtm/strategy/GTM_STRATEGY.md` — `baselayer-website\`
- `docs/reviews/README_REVIEW_S57.md` — `[local path]/Anthropic/franklin_memory`

**Note:** No hardcoded Windows paths were found in any `.py` file. All Python code uses `Path(__file__)`, `Path.home()`, or `MEMORY_SYSTEM_ROOT` env var. This is good.

**Recommendation:** Remove Windows paths from documentation files.

---

## 4. MEDIUM SEVERITY ISSUES

### M1 — SQL f-string patterns (safe but fragile)

**Files:**
- `scripts/author_layers.py` (line 298): `f"... IN ({placeholders})"` — placeholders are `?` marks joined, parameters are passed separately. **Safe.**
- `scripts/checkpoint.py` (lines 305, 343): Same pattern. **Safe.**
- `scripts/extract_facts.py` (line 115): `f"ALTER TABLE memory_facts ADD COLUMN {col} TEXT"` — `col` is hardcoded from a list `["predicate", "object_text", "qualifier"]`. **Safe** but would fail code scanning tools.
- `scripts/run_validation_study.py` (line 395): Same placeholder pattern. **Safe.**

**All are safe because the interpolated values are either `?`-placeholder strings or hardcoded column names, never user input.** However, this pattern could regress. The S55 audit noted "F-string SQL injection vectors eliminated (0 remaining)."

**Recommendation:** Add comments explaining safety, or refactor to avoid f-strings in SQL entirely.

### M2 — `__import__('time')` usage in cli.py

**File:** `scripts/cli.py` (line 885)
```python
conn.execute("...", (r["id"] + "_flag", r["id"], r["fact_text"], note, __import__('time').time()))
```

Using `__import__` inline is unconventional and could confuse linters. Not a security issue but a code quality issue. The `time` module is already importable at module scope.

**Recommendation:** Replace with a regular `import time` at the top of the function.

### M3 — Dependency pinning uses compatible release (~=)

**File:** `pyproject.toml`
```toml
dependencies = [
    "anthropic~=0.45",
    "chromadb~=0.6",
    "sentence-transformers~=3.0",
    "numpy~=1.26",
    "python-docx~=0.8",
    "requests~=2.31",
    "httpx>=0.24",
    "mcp[cli]~=1.2",
]
```

Compatible release (`~=`) is reasonable for a tool like this. `httpx>=0.24` is the loosest constraint. No known CVEs for these versions as of review date.

**Recommendation:** Acceptable as-is. Consider adding `httpx~=0.24` for consistency.

### M4 — PROGRESS.md relies solely on .gitignore

`docs/core/PROGRESS.md` is the most PII-dense file in the project (spouse name, colleagues, personal corrections, session-by-session biographical details). It is gitignored, but if someone runs `git add -f docs/core/PROGRESS.md` it would be committed.

**Recommendation:** Add a comment at the top of PROGRESS.md: `<!-- DO NOT COMMIT — contains personal data -->`. Also consider adding a pre-commit hook that rejects any `docs/core/PROGRESS.md` addition.

### M5 — No input length validation on MCP tool parameters

**File:** `scripts/mcp_server.py`

The `search_facts` tool has a limit cap (`min(limit, 100)`) which is good. But `recall_memories` and `trace_claim` have no input length limits on the query string. A very long query string could cause performance issues with embedding generation.

**Recommendation:** Add length limits to query parameters (e.g., `query[:500]`).

---

## 5. LOW SEVERITY ISSUES

### L1 — Placeholder API keys in documentation

Multiple docs and README contain `sk-ant-...` as example values. This is standard for documentation and acceptable. The `test_privacy.py` test suite explicitly validates this is safe.

### L2 — LIKE escaping already implemented

The S55 audit flagged missing LIKE metacharacter escaping. The `mcp_server.py` now has `_escape_like()` (line 70-72) and uses it in the LIKE fallback query (line 272). **Fixed.**

### L3 — Test method name references "aarik"

**File:** `tests/test_unified_brief.py` (line 531)
```python
def test_prompt_no_aarik_specific_pattern_names(self):
```

The test method NAME contains "aarik" but the test body does not contain personal data — it checks that prompts don't contain user-specific pattern names. The method name is descriptive and could be generalized to `test_prompt_no_user_specific_pattern_names`.

### L4 — baselayer.egg-info directory exists

The `baselayer.egg-info/` directory is on disk (from `pip install -e .`). It is not gitignored but Glob found it. It should be covered by `*.egg-info/` in .gitignore, which it is. **Verify it's not tracked.**

---

## 6. .GITIGNORE COVERAGE ASSESSMENT

The .gitignore is comprehensive. Coverage verification:

| Category | Pattern | Status |
|----------|---------|--------|
| Database | `data/database/` | COVERED |
| Vectors | `data/vectors/` | COVERED |
| Raw data | `data/raw/` | COVERED |
| Backups | `backups/` | COVERED |
| Entity maps | `entity_map.json` (3 locations) | COVERED |
| Environment | `.env`, `*.env` | COVERED |
| Python bytecode | `__pycache__/`, `*.pyc`, `*.pyo` | COVERED |
| Identity layers | `data/identity_layers/` | COVERED |
| Session progress | `docs/core/PROGRESS.md` | COVERED |
| Personal analysis | `docs/analysis/` | COVERED |
| Archive generated | `gtm/archive/generated/` | COVERED |
| Session transcripts | `reference/` | COVERED |
| User C case study | `gtm/research/BAVANI_CASE_STUDY*.md` | COVERED |
| Corpora data | `data/corpora/` | COVERED |
| Corrections data | `data/corrections*.json` | COVERED |
| Build artifacts | `*.egg-info/`, `dist/`, `build/` | COVERED |

**NOT covered (should be):**
| Category | Gap |
|----------|-----|
| GTM content with PII | `gtm/content/`, `gtm/strategy/`, `gtm/research/`, `gtm/outreach/` |
| Docs with PII | Multiple files in `docs/reviews/`, `docs/eval/`, `docs/plans/` |

---

## 7. CODE SECURITY

### SQL Injection: CLEAN
All SQL queries use parameterized `?` binding. The f-string patterns in 4 files build placeholder strings (`?,?,?`), not user input. The `_escape_like()` function in mcp_server.py properly escapes LIKE metacharacters.

### Command Injection: CLEAN
Only one `subprocess.run()` call found (`run_overnight.py` line 35). It passes `cmd` as a list (not shell=True) with hardcoded script paths. No user input in the command.

### Path Traversal: PROTECTED
ZIP import in `import_conversations.py` has ZipSlip protection (lines 474-480). Path resolution uses `resolve()` and checks with `startswith()`.

### MCP Server: SECURE
- stdio transport only (no network socket)
- `search_facts` has limit cap (100)
- LIKE escaping implemented
- Identity resource reads from local files only
- No write operations exposed through MCP tools

### Deserialization: NO ISSUES
No `pickle`, `yaml.load` (unsafe), `eval`, or `exec` with user input found. One `__import__('time')` in cli.py (safe but unconventional).

---

## 8. LICENSE & ATTRIBUTION

- Apache 2.0 license file exists: **YES** (`LICENSE`)
- Copyright notice: "Copyright 2026 the developer" — standard
- No vendored dependencies found
- No copied code without attribution detected
- All dependencies are standard PyPI packages with compatible licenses

---

## 9. PRIVACY SCRUB STATUS

The CLAUDE.md noted: "Privacy scrub pending: 6 critical files to delete, ~10 to anonymize, pyproject.toml author field."

### Files that should be DELETED before push (or gitignored):

1. **`data/entity_map.json`** — Already gitignored. Verify not tracked.
2. **`docs/core/PROGRESS.md`** — Already gitignored. Contains extensive personal history.
3. **`data/corpora/franklin_autobiography/entity_map.json`** — Pattern gitignored. Verify.
4. **`scripts/archive/_check_status.py`** — Contains personal correction terms. Delete or scrub.
5. **Entire `backups/` directory** — Already gitignored. Contains 5 copies of personal database.
6. **`data/raw/media/`** — Already gitignored. Contains personal images.

### Files that need ANONYMIZATION before push:

1. `pyproject.toml` — Author field (if desired)
2. `scripts/run_validation_study.py` — Eval prompts P1-P13 and multi-turn scenarios
3. `scripts/run_eval.py` — Eval prompts (10 prompts)
4. `scripts/assemble_brief.py` — TEST_CASES (lines 1556-1599)
5. `scripts/test_contradiction.py` — "Jordan has eczema" test case
6. `scripts/test_contradiction_detection.py` — "Techstars" parallels
7. `docs/core/PROJECT_OVERVIEW.md` — "the developer", GitHub URL
8. `docs/core/DECISIONS.md` — Personal correction details
9. `docs/reviews/CONTAMINATION_REVIEW.md` — "the developer" throughout
10. `docs/eval/BCB_FRAMEWORK.md` — "the developer" in data table
11. `docs/eval/EVAL_FRAMEWORK.md` — "User C" named
12. All `gtm/` files not already gitignored (see H4)
13. All `docs/` files listed in H5

---

## 10. RECOMMENDED ACTION PLAN

### Before push (BLOCKING):

1. **Create fresh repo** (L4 already decided). Do NOT push existing `.git` — it may contain secrets in history.
2. **Scrub Python scripts:** Generalize eval prompts in `run_validation_study.py`, `run_eval.py`, `assemble_brief.py` TEST_CASES, `archive/_check_status.py`.
3. **Decide on author attribution:** Keep or remove "the developer" from `pyproject.toml` and `LICENSE`.
4. **Add to .gitignore:** Either `gtm/` entirely, or scrub all personal references from gtm files.
5. **Anonymize docs:** Replace "the developer" with "User A", "User C" with "User C"/"Subject B", "User B" with "User B" across all docs/*.md files.
6. **Run `git ls-files`** on the new repo to verify no databases, entity maps, or identity layers are included.

### After push (soon):

7. Add pre-commit hook that rejects `*.db`, `*.sqlite*`, `entity_map.json`, `PROGRESS.md`.
8. Add `.github/workflows/` secret scanning (GitHub native feature).
9. Generalize test contradiction scenarios to remove biographical parallels.
10. Replace `__import__('time')` with proper import in cli.py.

---

## 11. POSITIVE FINDINGS

- **No real API keys or secrets anywhere in the codebase**
- **All SQL uses parameterized queries** — no injection vectors
- **ZipSlip protection** in import code
- **MCP server is stdio-only** — no network attack surface
- **Comprehensive .gitignore** covers databases, vectors, identity layers, entity maps
- **Privacy test suite exists** (`test_privacy.py`) with explicit key leakage checks
- **Config uses `MEMORY_SYSTEM_ROOT` env var** — no hardcoded paths in Python code
- **`_escape_like()` implemented** for LIKE query safety
- **No hardcoded Windows paths in any `.py` file** — all use `Path` objects
- **search_facts has limit cap** (100 max)
- **Fresh repo approach** (L4 DECIDED) eliminates git history risk
