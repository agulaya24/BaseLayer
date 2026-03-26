# Sonnet Handoff — Website + Pipeline Tasks
**Date:** 2026-03-09
**Source:** Opus Session 81 continuation
**Context:** Sonnet completed REVIEW_RESULTS.md (7-phase code review, commits c7fbaee + f805b5f). Opus completed Journey/Hero/sitemap updates, CLAUDE.md cleanup. Below are remaining mechanical tasks for Sonnet.

---

## 1. Try It Page — Visual Contrast + Content Updates
**File:** `C:\Users\Aarik\Anthropic\baselayer-website\components\TryIt.tsx`

### 1a. Visual contrast improvements
- Page is "flat" visually. Add:
  - Accent borders or subtle gradients to section dividers
  - More visual distinction between the cost table, destination cards, and CLI sections
  - Consider card hover states with border-accent transitions

### 1b. Cost clarification
- Current cost examples don't explicitly state they include ALL three models
- Update the note below the cost table: "Uses Haiku (extraction), Sonnet (authoring), and **Opus (composition)**" — bold Opus since user asked if costs include Opus. Answer: YES.
- Actual S81 pipeline costs per subject ranged $0.25–0.37 (author+compose only, extraction was already done). Full pipeline including extraction would be higher.

### 1c. Claude Code workflow
- Update the Claude Code tab to be simpler for most users:
  - "Drop your brief file into your project root"
  - "Add to CLAUDE.md or .cursorrules: `Read baselayer_identity.md for identity context.`"
  - Note: most users will drop the file and let Claude Code find it
- Consider creating a `baselayer_identity.md` template that explains to Claude Code what the brief is and how to use it

### 1d. Data pipeline testing
- **SEPARATE WORK STREAM** — not a website task
- Run pipeline with small variations (different chunk sizes, different extraction caps) to stress-test
- Track and compare output quality

---

## 2. Research Page — UX + Content Fixes
**File:** `C:\Users\Aarik\Anthropic\baselayer-website\components\Research.tsx`

### 2a. Fix expand button UX
- Current: dead `>` on the left + dropdown chevron on right = confusing
- Fix: make the whole row clickable with a single chevron indicator (right side). Remove any left-side arrow that doesn't do anything.
- Alternatively: single left-side rotating arrow, remove right chevron

### 2b. Add provenance evaluation results
- The provenance section describes the framework but shows NO actual results
- Data exists from Phase 1 runs on Marks + Aarik:
  - Read `C:\Users\Aarik\Anthropic\memory_system\docs\eval\PROVENANCE_EVAL_REPORT.md` for actual BA/PC scores
  - Add a results table or stat cards showing the mechanical evaluation scores
  - Include what percentage of claims had vector provenance matches

### 2c. Expand compose variation descriptions
- Current: each variation is just 2 sentences — too thin
- For each V1-V6, add:
  - What the prompt actually changed (1-2 sentences)
  - A brief example of output difference (how the brief reads differently)
  - Why it scored how it did
- V4 data: FP guards + tension-action pairs woven into prose — best balance
- V5: removed availability index — marginal difference
- V6: compressed format — lost detail, machine-readable but poor human utility

### 2d. Fix download report
- Download buttons link to `/reports/*.md` files in `public/reports/`
- Check: are all 7 .md files present and non-empty? (They are: ablation-study.md, bcb-framework.md, compose-variations.md, compression-format.md, provenance-eval.md, research-summary.md, twin2k-benchmark.md)
- Issue: browser may open .md instead of downloading. Fix: either rename to .txt, or add proper Content-Disposition headers, or convert to PDF
- **User request:** Put ALL research in the downloadable report. Rewrite for public consumption. Add a simplified abstract as the first section, then technical content follows. The research-summary.md should be the comprehensive report.

---

## 3. Hero Page — Tooltip Layer
**File:** `C:\Users\Aarik\Anthropic\baselayer-website\components\Hero.tsx`

### Already done by Opus:
- Updated all 5 slides with V4 prediction data
- Changed "deletable" to "yours to modify"
- Changed "Contradictions" to "Tensions"
- Bolded and increased text size for "FACTS" and "IDENTITY MODEL" headers

### Still needed:
- Add tooltip layer for key terms on the homepage:
  - "identity brief" → "A compressed profile of how someone thinks, decides, and reacts — generated from their writing"
  - "behavioral compression" → "Distilling thousands of pages into the patterns that actually predict behavior"
  - "provenance" or "traces back to source facts" → "Every claim in the brief links to the specific sentence it came from"
  - "identity model" → "Not a chatbot persona — a structured model of behavioral patterns with directives for AI systems"
- Use a subtle dashed underline + hover tooltip (similar to Research.tsx Tooltip component)
- Keep simple — terms that a non-technical reader would pause on

### Language approachability (broader pass):
- The site should be approachable to non-technical stakeholders who might apply this to their industry
- Key principle: use simpler terms where possible, but keep rigor. Tooltip layer handles the gap.
- "Epistemic axioms" → just say "core beliefs" on the homepage
- "Behavioral compression" → "pattern extraction" or just explain it naturally
- Don't dumb down the research page — that's for people who want depth

---

## 4. File Structure — Move marks/buffett into subjects/
**These are pipeline-side changes, not website changes.**

### Current state:
- `C:\Users\Aarik\Anthropic\buffett_memory\` — at Anthropic root
- `C:\Users\Aarik\Anthropic\marks_memory\` — at Anthropic root
- Should be inside `C:\Users\Aarik\Anthropic\subjects\` like all other subjects

### Steps:
1. Move `buffett_memory/` → `subjects/buffett_memory/`
2. Move `marks_memory/` → `subjects/marks_memory/`
3. Update `scripts/generate_tension_data.py` — paths already fixed by Phase 7 to use env vars, but verify
4. Update any hardcoded references in website data generation scripts
5. Update `.gitignore` entries (Phase 7 added `buffett_memory/` and `marks_memory/` at root)
6. Test: `baselayer stats` and website data generation still work

### Also noted:
- `subjects/` also contains: `baselayer_meta/`, `baselayer_meta_v1/`, `goertzel_memory/`, `howard_marks_memos/`, `roman_memory/`, `mk_test/`, `lesswrong_clt/`, `paul_graham_qwen/`, `twin2k/`, `buffett_letters/`
- Some of these may be duplicates or test data. Aarik should review.

---

## 5. Pipeline Runs Needed

### 5a. Bavani's data
- Location: `C:\Users\Aarik\Anthropic\subjects\bavani_memory\`
- State: has database (memory.db), has V4 layers (anchors_v4.md, core_v4.md, predictions_v4.md), NO brief
- **Needs:** `baselayer compose` (or full `baselayer run` if re-extraction desired)
- This is PRIVATE data — output should NOT go on the website

### 5b. Aarik's data refresh
- Location: `C:\Users\Aarik\Anthropic\memory_system_v4\`
- **Needs:** re-author + re-compose with V4 pipeline
- This is PRIVATE data — output should NOT go on the website

### 5c. Paul Graham
- Location: `C:\Users\Aarik\Anthropic\subjects\paul_graham\`
- State: 28 essays, 272 facts extracted, NO identity layers, NO brief
- **Needs:** `baselayer author --subject "Paul Graham"` then `baselayer compose`
- This WOULD go on the website as a new case study

---

## 6. Deferred Items from REVIEW_RESULTS.md

### Aarik decisions (RESOLVED by Opus):
1. `assemble_brief.py` — **KEEP as serving layer for now.** MCP server + CLI commands depend on it. Post-launch: migrate to read unified brief directly.
2. `detect_contradictions.py` at root — **KEEP at root.** Label as "experimental enrichment — feeds tension data to V4 compose." Not officially step 5 but provides optional input.
3. `tests/test_agent_pipeline.py` (18 failures) — **REMOVE.** Tests dead API functions deleted in S79.
4. `tests/test_unified_brief.py` (13 failures) — **REMOVE.** Tests archived run_validation_study.py.

### CLAUDE.md updates done by Opus:
- Removed 4 archived scripts from Key Scripts table
- Updated author_layers description
- Added detect_contradictions and generate_tension_data

### Done by Opus:
- `docs/REVIEW_PLAN.md` → added to `.gitignore`
- `docs/plans/` → added to `.gitignore`
- `docs/REVIEW_RESULTS*.md` → added to `.gitignore`

### Still needed:
- `docs/plans/CONTRADICTION_WORKFLOW_PLAN.md` → scrub "Aarik" identifier
- Remove the two dead test files listed above

---

## 7. Local Deployable Version (TODO — not this session)
- User wants an app/exe they can open locally to review identity layers
- Separate from website — would show Aarik's data, Bavani's data, or any private data
- Options: Electron app, local Next.js dev server, simple Python Flask/Streamlit app
- **Parked for later planning session**

---

## 8. XML Sitemap
- **Already handled.** Next.js auto-generates `/sitemap.xml` from `app/sitemap.ts`
- Opus added `/research` route to the sitemap
- No manual sharing with Google needed — Google discovers `/sitemap.xml` automatically
- Can optionally submit via Google Search Console for faster indexing

---

## 9. Documentation Crawl
- Verify all docs in `docs/core/` and `docs/eval/` are aligned with current state (4-step pipeline, V4 compose, ablation results)
- Sonnet already fixed: ARCHITECTURE.md, DECISIONS.md, DESIGN_PRINCIPLES.md (commits 77e896a, 28393a7, aa3c214)
- Check for any remaining stale references to 14-step pipeline, Collective review, or removed scripts
- **Design principles:** Aarik wants these on the website too. Consider adding a "Design Principles" expandable section to the Journey page.

## 10. Examples Directory
- **DONE by Opus:** Created `examples/` directory with all 7 public subjects (4 files each: anchors, core, predictions, brief)
- **DONE:** Examples README.md created
- buffett/marks are already in `subjects/` (root-level copies no longer exist)
- File structure cleanup may already be done — verify

## 11. README Updates
- **DONE by Opus:** Updated test counts, token sizes, cost data, session counts, removed adversarial review reference
- Review the full README for any remaining stale content (validation table scores may need updating)

## Priority Order for Sonnet
1. **Research page fixes** (expand UX, provenance results, compose depth, download fix) — most visible quality gap
2. **Try It visual contrast + cost clarification** — quick wins
3. **Remove dead test files** — `tests/test_agent_pipeline.py` + `tests/test_unified_brief.py`
4. **Scrub CONTRADICTION_WORKFLOW_PLAN.md** — "Aarik" identifier
5. **Documentation crawl** — verify alignment across all docs
6. **Pipeline runs** (Paul Graham, Bavani compose, Aarik refresh) — separate terminal
7. **Report rewrite for public consumption** — longer task, may need Opus review
8. **Design principles on Journey page** — expandable section
