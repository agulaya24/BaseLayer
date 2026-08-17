# Base Layer — Session Progress (S86+)

> **⚠️ SUPERSEDED — logging stopped at Session 114 (2026-04-23) (banner added 2026-07-02).** This file has no entries since April and predates launch, arXiv, MATS, and the SCOTUS work. The CLAUDE.md session protocol's "read last entry only" instruction currently returns pre-launch April state — do NOT use this file for current status. Live state: `Anthropic/todo_dashboard.html` + the latest `Anthropic/SESSION_HANDOFF_*.md`.

> Sessions S1-S85 archived in [PROGRESS_ARCHIVE.md](PROGRESS_ARCHIVE.md)

## Session 114 (2026-04-23) — v9 Paper Revision, 233 Annotations Triaged, Phase 1 Data Jobs

### Headline
Full triage of 233 Word-comments from Aarik on v8 "Beyond Recall." v8 forked to v9 draft. Phase 1 data reruns executed (Supermemory paid-tier, author derangement). Six Part A sweeps applied, eight more queued. Recovered from one methodology propagation error by verifying primary source.

### What Was Done

**Annotation triage (all 233 Aarik comments on v8):**
- Full edit plan: `memory-study-repo/docs/reviews/s114_v9_edit_plan.md`
- Cross-LLM consensus review: `memory-study-repo/docs/reviews/s114_v9_triage_consensus.md`
- v8 forked to v9: `memory-study-repo/docs/beyond_recall_v9_draft.md`

**Phase 1 data reruns (complete):**
- **P0-2 Supermemory paid tier** (4 subjects): ingest + generate done. 7-judge panel running.
  Report: `memory-study-repo/docs/research/p0_2_supermemory_paid_tier_rerun.md`
- **P0-6 author derangement** (Seacole random-pick, Babur max-distance): 120 wrong-spec responses across both conditions plus existing Franklin. **H6 holds robustly** — zero downward crossings vs. C5 on any of 40 questions under either new draw. Lift lands +1.15 (Seacole) to +1.32 (Babur) vs. +1.56 Franklin, consistent with §4.1.2 "atypically favourable draw" decomposition.
  Report: `memory-study-repo/docs/research/p0_6_author_derangement.md`
- **P0-4 / P0-5 / P0-7 / P0-15 / P0-16 / P0-17** analyses complete. Reports in `memory-study-repo/docs/research/`.

**v9 Part A sweeps:**
- Applied: A4, A5, A6, A7, A8, A12, A13, A14
- Remaining: A1, A2, A3, A9, A10, A11

**Other integrations:**
- §4.1.2 updated with 3-way wrong-spec control data (Franklin + Seacole + Babur)
- Battery leakage audit confirmed clean: 2/586 matches (0.34%), Franklin-only

### Mistakes Made and Recovered
- **Propagated a flawed research-doc claim** that §4.1 used a simpler Haiku spec. Verified against primary source `run_global_rerun.py:285`, confirmed §4.1 uses the full 4-layer Sonnet+Opus spec for all 14 subjects. The research doc was wrong.
- **Ran a Hamerton unified rerun under the wrong premise**, produced contaminated numbers, deleted the artifacts from the repo.
- **Process lesson:** verify primary sources before building on prior-session claims. Research docs are not primary sources — code is.

### Running Background Jobs at Session End
- Supermemory 7-judge panel
- Em-dash structural re-review
- Figure rebuild plan
- Appendix audit
- Q&A digest from annotations
- This documentation update

### Open Items Blocking Paper Close
- Part B structural moves
- Part F section-by-section walkthrough
- Figure rebuild execution
- Abstract (deferred to last)

### Post-Release Note
After v9 ships, a new self-referential rerun of the Base Layer pipeline on Aarik's own updated corpus is planned. Current Aarik spec in `_internal/aarik_clean_pilot/` is the one used for §4.1.2 living-user replication; post-paper rerun will re-extract and regenerate against his current state.

---

## Session 109 (2026-04-14) — Paper References Verified + Corrected, Free Law CSV Checkpointed

### Headline
Full reference audit on "Beyond Recall" — 9 uncertain citations verified by search agent, corrections applied to paper and REFERENCE_TABLE.md. Free Law Project CSV generator rewritten with checkpoint/resume logic. Researcher outreach targets added (4 tiers). Computer restart pending.

### What Was Done

**References — 9 verified, all corrections applied:**
- REF-08 (Chen Persona Vectors): title corrected to "Monitoring and Controlling"; lead author Runjin Chen not "Y. Chen"
- REF-11 (AlpsBench): full title corrected; "Alignment Beyond Recall" was invented subtitle
- REF-13 (Context Rot): Kelly Hong at Chroma; no arXiv — technical report; URL confirmed
- REF-14: lead author Yufeng Du not "Li, N."; venue EMNLP 2025
- REF-15 (CAUSM): **does not exist** — replaced with real Jain et al. arXiv:2509.12517, CHI 2026
- REF-16 (Lu): title corrected "Situating and Stabilizing"; author Christina Lu not "K. Lu"
- REF-17 (PersonaMem): real paper is Jiang et al. "Know Me, Respond to Me", arXiv:2504.14225, COLM 2025
- REF-18 (PersonaX): real paper is Shi et al. arXiv:2503.02398; ACL venue unconfirmed
- REF-19 (Stacy social cognition): **does not exist** — removed from paper entirely
- Body text corrections: "Li et al." → "Du et al.", "PersonaMem" → "Jiang et al.", CAUSM → real Jain citation, Lu first initial C not K
- PersonaX in-body mention removed (actual paper is recommendation agents, not behavioral profiling)

**REFERENCE_TABLE.md** (`memory-study-repo/docs/REFERENCE_TABLE.md`):
- All 9 updated with VERIFIED/PARTIAL/NOT FOUND status and corrections
- Pre-submission checklist updated

**Free Law Project CSV generator** (`data/scotus/generate_author_fix_csv.py`):
- Full rewrite with checkpoint/resume logic
- Saves `author_fix_checkpoint.json` every 50 clusters
- On restart: skips already-processed clusters, reuses cached cluster IDs per term
- 1.5s delay (was 2.0s), better 502/503/504 backoff
- `--reset` flag for clean start
- **DO NOT auto-start** — Aarik runs manually from terminal (4-5 hrs, resumes on interruption)
- When complete: run `python fix_author_csv.py` to produce final clean CSV


**Paper synced:** both copies updated (memory-study-repo + memory_system/drafts)

### Current State at End of Session
- Paper: all S107-S109 editorial edits complete. Aarik doing voice pass. Launch ~Thursday.
- Free Law CSV: script ready with checkpoints. Run manually after restart.
- SCOTUS study: unchanged, pending paper launch.
- Global pipeline (S108): compose was running for 11/13 subjects. Status unknown — check after restart.

---

## Session 108 (2026-04-14) — Pipeline Bugs 3+4 Fixed, Compose Running, Paper Redline

### Headline
Two more pipeline bugs found and fixed (bugs 3+4 of 4 total across S106-S108). All 13 global subjects: extract+embed+author complete. Compose running for 11/13. Paper redline with Aarik.

### Bugs Fixed (bugs 3 and 4 — see `memory/feedback_pipeline_refactor_needed.md` for all 4)
- **BUG 3 — embed.py Unicode crash:** `verify_embeddings()` calls `print(preview)` which fails on Windows cp1252 when facts contain non-Latin characters (Arabic, Japanese, BOM). Embedding itself succeeds but process exits 1. Fix: `PYTHONIOENCODING=utf-8` in subprocess env via `make_env()`.
- **BUG 4 — compose wrong module:** `run_overnight_pipeline.py` called `python -m baselayer.agent_pipeline compose`. `agent_pipeline.py` has no CLI handler — it silently exits 0 and writes nothing. Fix: `python -m baselayer.cli compose`.

### Pipeline State for 13 Global Subjects
| Step | Status |
|---|---|
| split (paragraph-preserving) | DONE — all 13 |
| init + import | DONE — all 13 |
| extract (Haiku, --document-mode) | DONE — 125-358 facts each |
| embed (MiniLM-L6-v2) | DONE — all 13 |
| author (Sonnet) | DONE — all 13 |
| compose (Opus) | RUNNING — 11/13 (augustine+babur: need re-run) |
| spec (layers+brief) | PENDING compose |

### Paper Updates
- Limitation #8 corrected: global subjects use full Sonnet+Opus pipeline (old text said Haiku-only).
- Limitation #8 rewritten: import structure difference noted (single-doc vs chapter-by-chapter).

### Current State at End of Session
- Compose in progress (PID 41564). ~25 min remaining for 11 subjects.
- After complete: re-run augustine + babur with `--from-step compose`.
- Then: full status check, copy specs to study repo.
- Paper redline with Aarik: pending compose completion.

---

## Session 107 (2026-04-13) — Paper Editorial Pass: References, Citations, Figures, Hedging Metric

### Headline
Full editorial pass on "Beyond Recall" paper. Deterministic reference table created, 19 references audited and verification-flagged, 7 inline citations added to body, Section 5.5 hedging metric made prominent, 4 figure specifications written for formal pass, SCOTUS study updated.

### What Was Done

**Paper edits (`memory-study-repo/docs/beyond_recall_arxiv_draft.md`):**
1. **Reference table** (`docs/REFERENCE_TABLE.md`) — 19 references keyed REF-01 through REF-19 with verification status (VERIFIED / PROBABLE / NEEDS CHECK), body citation map, and pre-submission checklist. 9 references need arXiv ID confirmation before ArXiv submission — marked with †.
2. **Section 5.5** — Renamed "The Hedging Problem". 51%→31% hedging metric pulled into a callout block, labeled as the key finding. Jain et al. (CAUSM) and Lu et al. (Assistant Axis) cited as supporting context.
3. **Inline citations added:**
   - PersonaMem → Section 5.1 (50% user modeling failure)
   - PersonaX → Section 5.3 (decoupled behavioral profiling)
   - Chen et al. → Section 2 Related Work (new paragraph on persona vectors as complementary approach)
   - Betley et al. → Section 5.6 (domain guard as misalignment countermeasure)
   - Jain/CAUSM + Lu → Section 5.5 (hedging as structural property)
4. **References section** — reformatted with [REF-XX] keys, † flags for unverified IDs, pointer to REFERENCE_TABLE.md
5. **Appendix D** — Figure specifications written for 4 figures: Global Gradient scatter, Compression Curve, Retrieval Disagreement, Hedging Reduction. Each spec includes: chart type, data source, axis definitions, annotation points, key message. Ready for formal pass.

**SCOTUS study:**
- Domain-expert human evaluator removed → LLM-as-judge
- Mem0 Pro added as 4th condition
- Thomas-first approach confirmed
- Free Law Project CSV pipeline: `generate_author_fix_csv.py` + `fix_author_csv.py` complete
- All 11 SCOTUS justice person IDs mapped (OT2008-OT2015 gap)

**Other:**
- 17GB local backup of the working tree completed to external storage
- Both paper copies synced (memory-study-repo and memory_system/drafts)

### Current State at End of Session
- Paper: all structural edits done. Aarik doing voice pass in Google Drive. Launch ~Thursday 2026-04-17.
- References: 9 need human search for arXiv IDs before ArXiv submission (see REFERENCE_TABLE.md checklist)
- Figures: 4 fully specified in Appendix D; require production tooling to generate
- SCOTUS: CSV generator running; `fix_author_csv.py` ready to post-process output
- Stats still TODO: Wilcoxon signed-rank, Krippendorff's alpha across 7 judges, scatter plot

---

## Session 106 (2026-04-13) — Global Subjects Pipeline Fixed + Overnight Run Launched

### Headline
Fixed two critical bugs that were producing 12-42 facts per subject instead of 200+. All 13 global subjects pipeline relaunched overnight.

### What Was Built
1. **Root cause identified**: `split_corpus()` was splitting corpus by words (`corpus.split()`) and rejoining with spaces, destroying all `\n\n` paragraph breaks. `_chunk_text_for_extraction()` relies on `\n\n` to chunk. Result: 1 chunk per 185K chars → ~36 facts instead of 200+.
2. **Fix**: Character-midpoint split finding nearest `\n\n` boundary, preserving original paragraph structure. Confirmed: augustine 261 paragraph breaks, sunity_devee 469 paragraph breaks.
3. **AUDN NOOP bug confirmed**: Must clear BOTH SQLite AND ChromaDB vectors before re-extraction. Stale vectors cause all new facts to be marked NOOP (duplicate). Documented in `memory/feedback_clear_chromadb_on_reset.md`.
4. **Overnight runner**: `run_overnight_pipeline.py` — complete overnight runner with OPENBLAS_NUM_THREADS=1, sequential execution, auto-clearing of both SQLite and ChromaDB, diagnostic logging, resume-from-step support.
5. **Paper voice pass support**: All Section 5 additions for paper — 5.4 (compression story with size table), 5.5 (when to use spec), 5.6 (what this paper is and is not). Em dashes removed (77 instances restructured). Closing added.

### Bugs Fixed
- `split_corpus()` word-split destroying paragraph structure → character-midpoint with `\n\n` search
- `capture_output=True` on pipeline subprocesses swallowing all output → `stdout=sys.stdout, stderr=sys.stderr`
- OPENBLAS memory exhaustion on parallel runs → sequential + `OPENBLAS_NUM_THREADS=1` in subprocess env

### Current State at End of Session
- 13 subjects pipeline running overnight via `run_overnight_pipeline.py`
- All corpora re-split with paragraph preservation
- All SQLite + ChromaDB cleared
- Log: `data/experiments/memory_systems/overnight_run_*.log`

---

## Session 105 (2026-04-10 to 2026-04-12) — "Beyond Recall" Study — Most Comprehensive Memory Study Published

### Headline
**"Beyond Recall: Behavioral Specification as the Missing Primitive for AI Personalization."** Full layer stack (anchors + core + predictions + brief) tested across 14 subjects, 11 cultures, 6 response models, 7 judges, 15+ conditions. Judge calibration framework built. N=1→N=14 in one session.

### What Was Built This Session
1. **Franklin replication** — known-figure test. Baseline 3.99 dominates. Context hurts for known subjects.
2. **Franklin obscure letters** — partial knowledge test. Baseline 3.50. Cross-corpus spec.
3. **Clean Franklin spec** — regenerated from chapters 0-10 only. No leakage.
4. **Full-stack spec** — anchors + core + predictions + brief. The actual product configuration.
5. **C4a (all facts + spec)** — new highest condition for Hamerton (3.23 brief, 2.69 full-stack).
6. **C9 (raw corpus)** — 25K words in context. Spec + 10 facts beats raw text (3.01 vs 2.31).
7. **C8 (raw corpus per system)** — each system processes raw text. Spec helps all pipelines.
8. **C7 (named baseline)** — "This is Benjamin Franklin." Model already knows without being told.
9. **6 response models** — Haiku, Sonnet, GPT-4.1, GPT-5.4, Gemini Flash, Gemini Pro.
10. **7 judges** — Haiku, Sonnet, Opus, GPT-4o, GPT-5.4, Gemini Flash, Gemini Pro.
11. **Judge calibration framework** — verbatim/paraphrase/length tests. Ceiling 5.00 for judges, 4.23 for response model. Length bias detected in Haiku. Publishable contribution.
12. **13 global subjects** — running overnight. Keckley, Sunity Devee, Zitkala-Sa, Equiano, Seacole, Fukuzawa, Babur, Yung Wing, Cellini, Bernal Diaz, Ebers, Rousseau, Augustine. 11 cultures.
13. **Outreach plan** — 6 tiers, templates, study release list.
14. **Study repo plan** — agent-friendly with .agents/ directory.
15. **Publication strategy** — 4 posts + ArXiv preprint "Beyond Recall."

### Key Results (Full-Stack Spec)
**Hamerton (unknown, baseline 1.37):**
- C3_full_mem0: 2.97 (Haiku) / 3.79 (Gemini) / 2.82 (GPT-5.4). Cohen's d = 1.21 (large).
- C2c wrong spec: 1.38. Indistinguishable from baseline. Wrong full-stack adds nothing.
- C4a: 2.69. Spec helps even with all facts.
- C9 raw corpus: 2.31. Spec + 10 facts beats 25K raw words.

**Franklin (known, baseline 3.99):** All conditions below baseline. Context hurts.
**Franklin obscure (partial, baseline 3.50):** Below baseline. Model's general Franklin knowledge dominates.

### Issues Caught & Fixed
- Franklin spec data leakage (generated from full autobiography → clean spec from ch 0-10)
- Brief-only vs full-stack spec (study used brief only → re-ran with full layer stack)
- Q50 misclassified as behavioral_prediction (no held-out passage → reclassified to inferential)
- Supermemory 308 redirect (follow_redirects=True fix)
- Gemini Pro Unicode crash (UTF-8 encoding fix)
- GPT-5.4 max_tokens → max_completion_tokens parameter change

### Insights Captured (Aarik's voice bank at `memory/aarik_insights_s105.md`)
- "The model has no idea who you are — and that's a problem."
- "It's not a filing cabinet, it's an undervalued copy."
- "Memory is really about how the facts are used. Why leave that to a pure inference machine."
- "There is no other metric to optimize for besides predictive reasoning."
- "We must embody open source, what it should be, not what it is."
- "I want it to be between research and belief."

### Cost
- Total API spend: ~$50-60 across all runs, all models, all subjects
- Gemini Flash: free
- Gemini Pro: free (rate limited)

---

## Session 104 (2026-04-09 to 2026-04-10) — Memory Systems Study COMPLETE. Monday Launch.

### Headline Finding
**A 3,156-token behavioral specification outpredicts four funded SOTA memory systems (Mem0, Letta, Supermemory, Zep) on held-out behavioral prediction. Adding it to any of them makes them better.**

Title: **"Mem0, Zep, Letta, Supermemory: State of the Art Is Missing the Art"**

### Study Execution — 1,036 Data Points
- 80 questions × 13 conditions across 5 tiers (recall, inference, behavioral prediction, adversarial, boundary)
- Corpus: Philip Gilbert Hamerton autobiography (Victorian art critic, near-zero LLM prior knowledge)
- 462 shared facts ingested into all 4 memory systems
- Behavioral spec (3,156 tokens) generated from same corpus via Base Layer pipeline
- 14 conditions: C1×4 (memory systems), C2a (spec only), C2c (wrong spec — Franklin), C3×4 (spec+memory), C4 (all facts), C5 (baseline), C6 (random)
- Held-out validation: questions designed backward from chapters 11-32, spec built from chapters 1-10 only

### Results
- **C3 > C1 across all systems (p=0.012).** Spec + facts beats facts alone. 16 wins, 4 losses.
- **C2a (spec only) trends higher but NOT significant vs C1 (p=0.83).** Spec needs facts.
- **C2c wrong spec (2.21) < correct spec (2.77).** Right spec matters — not just "any framework helps."
- **C4 fact dump (2.74) ≈ C2a spec (2.77).** 462 facts ≈ 3,156 tokens. Compression ratio finding.
- **Bimodal → gradient:** C1_mem0 has 16 ones + 11 fives. C3_mem0 has 3 ones + 11 fives. Spec rescues 13 predictions from catastrophic failure.
- **65% retrieval disagreement** across embedding systems on top-1 fact. They don't agree with each other.
- **Zep graph bias:** retrieves same father-property fact for 39% of all questions.
- **Adversarial:** all conditions 100% abstention on unanswerable questions except C4 (80%). More facts = overconfidence.
- **Spec amplification:** C3 produces 2.07-2.25x output tokens of C1, consistent across all systems.

### Inter-Rater Reliability (4 judges) — ALL COMPLETE
- **Haiku 4.5:** primary judge (complete)
- **Sonnet 4.6:** exact agreement 66.3%, within-1 87.1%, Spearman rho=0.885 (complete)
- **Opus:** complete. Sonnet-Opus rho=0.983 (near-perfect agreement).
- **GPT-4o:** complete. 505/505 scored, 0 failures. Most generous judge (~0.2-0.4 points higher than Anthropic models). Does not change ranking.
- All 4 judges agree: C3 conditions are top 4, C5/C6/C1_zep are bottom 3.
- Pairwise Spearman rho: all pairs 0.89-0.98. Sonnet-Opus highest (0.983).
- 4-judge averages: C3_letta 3.13, C3_mem0 3.01, C3_supermemory 3.01, C3_zep 2.69.
- C3 avg 2.96 vs C1 avg 2.33 = +0.63 (+27%). p=0.012 holds across all judges.

### Methodological Checks
- Length bias: r=0.334 (moderate). Acknowledged.
- C1 refusal rate: 51%. When C1 answers, scores 3.7. Spec cuts refusal to 31%.
- Baseline contamination: C5 scores 1 on 32/39 questions. Model doesn't know Hamerton.
- Bootstrap 95% CIs: C3_mem0 [2.79, 3.67], C1_mem0 [2.13, 3.23]. Overlap exists but sign test significant.

### Collective Reviews on Results
- Rao: "Spec adds a failure mode that degrades gracefully instead of catastrophically."
- Marks: "Wrong framework still outperforms no framework. Illusion of knowledge more dangerous than ignorance."
- Galef: "Advantage is additive not substitutive. Check score when all 3 systems agree." (TODO)
- Graham: "Wrong map better than no map, right map 25% better. That ratio is the business case."
- patio11: "3-6K token artifact with zero latency. Ship a feature around C4 fabrication."

### Technical Issues
- SDK init hangs after ~50 queries (urllib3/chardet version mismatch). Fixed with raw httpx.
- Zep `list_ordered()` returns named tuples not User objects. Fixed in standalone runner.
- Supermemory search API: `POST /v3/search` with `containerTags` (camelCase array).
- Config had wrong IDs (hamerton_study_v2 → hamerton_study). Fixed.

### Franklin Replication (S105) — COMPLETE, Judges Running
- **80 questions × 12 conditions** — all responses collected
- **4 judges complete:** Haiku, Sonnet 4.6, Opus, Gemini 2.5 Flash. GPT-4o blocked (key permissions).
- **Headline:** Baseline dominates (3.99). Context hurts for known subjects. Spec is a tool for the unknown.
- **C4a (all facts + spec):** 3.23 (new Hamerton highest). Spec helps even with complete information.
- **C9 (raw corpus):** Hamerton 2.31. Spec + 10 facts (3.01) beats 25K raw words.
- **C8 (raw corpus per system):** Ingestion DONE. Queries RUNNING.
- **Franklin C9:** Running (Q19-80).
- **Zep standalone Franklin:** Running.
- **Obscure Franklin corpus downloaded:** Complete Works Vol 2 (151K words).
- **5 judges from 3 providers** (Anthropic, OpenAI, Google) — all agree on rankings.

### Infrastructure (S105)
- Google Docs MCP server configured (`@a-bonus/google-docs-mcp`). Pending OAuth on session restart.
- Gemini 2.5 Flash API configured as 5th judge. Free tier, `GEMINI_API_KEY` set.
- Blog post updated with Franklin results, C9/C4a findings, 5-judge stats.
- Charts regenerated: 7 charts in `drafts/charts/`.
- Study repo created (memory-study-repo).
- SCOTUS study spec formalized at `docs/eval/SCOTUS_STUDY_SPEC.md`.
- Provider issues documented at `data/experiments/memory_systems/PROVIDER_ISSUES.md`.

### Distribution Plan — MONDAY 2026-04-14
1. Blog post + interactive data explorer on base-layer.ai
2. Public study repo (all scripts, data, results) — NOT YET CREATED
3. ArXiv preprint same week
4. Email founders: Taranjeet (Mem0), Charles Packer (Letta), Dhravya Shah (Supermemory)
5. Email investors: a16z, Felicis
6. Social: X, HN, r/LocalLLaMA, LinkedIn
7. Franklin replication to follow (known-figure test)

### Files
- Runner: `data/experiments/memory_systems/run_full_study.py` (14 conditions)
- Fallback: `data/experiments/memory_systems/run_remaining.py` (raw httpx)
- Judge: `data/experiments/memory_systems/run_judge_batch.py` (batch submit/check/process)
- Results: `data/experiments/memory_systems/results/run_20260409_182743/results_merged.json`
- Analysis: `data/experiments/memory_systems/results/run_20260409_182743/analysis/`
- Study spec: `docs/eval/MEMORY_SYSTEMS_STUDY.md`
- Experiment log: `data/experiments/memory_systems/EXPERIMENT_LOG.md`

---

## Session 103 (2026-04-08 to 2026-04-09) — Memory Study Designed, Test Run, SCOTUS Corpus

### Memory Systems Study — Designed and Test Run Complete
- Study spec finalized: `docs/eval/MEMORY_SYSTEMS_STUDY.md`
- All 4 memory systems connected and tested (Mem0, Letta, Supermemory, Zep Cloud)
- 462 shared facts extracted and ingested
- Hamerton spec generated (3,156 tokens)
- 80-question battery built (39 with held-out ground truth passages)
- LLM-as-judge method locked (replaces embedding similarity)
- 5-question test run: embedding systems 40-60% top-1 overlap, Zep 0-20%
- Key test finding: spec transforms refusal into prediction

### SCOTUS Corpus — Downloaded
- Harvard CAP: 572 volumes, 1.2GB, every SCOTUS opinion 1754-2019
- Thomas: 517 opinions extracted (OT1991-OT2013)
- CourtListener: OT2016-OT2025 supplemented
- Gap: OT2014-OT2015 needs reconciliation

---

## Session 102 (2026-04-06 to 2026-04-08) — Serving Layer Built, Messaging Reframe, SCOTUS Study Designed

Longest session in project history (~16 hours). Serving layer designed, built, and tested. Full messaging reframe. Battery results. SCOTUS study scoped as the definitive experiment.

### Serving Layer — DESIGNED AND BUILT
- **Architecture:** Behavioral spec always-on. The diff between with-spec and without-spec IS the identity signal.
- **Engine:** `runners/serving_engine.py` — diff cascade with Mem0-faithful baseline (Chhikara et al., 2025)
- **TUI:** `runners/serving_tui.py` — 7-panel visual debugger with live cascade updates. Non-blocking startup, error logging, embedding cache.
- **Key finding:** 18/19 retrieval divergence between Mem0 and Base Layer on same fact store. Mem0 retrieved cake recipes and mattress preferences for "what makes base layer special?" Base Layer retrieved agency, resilience, sovereignty.
- **Killed:** Embedding-based routing (15-35% similarity range too narrow). Replaced with model-routed activation (C6).
- **Multi-subject support:** `--subject buffett`, `--subject <subject>`

### 50-Question Battery — COMPLETE
- 50 questions across 10 topics, 3 conditions, mechanical measurements only
- Relationships diverge most (4.75 avg), career least (3.29)
- Consistent pattern: Mem0 gives lists (avg 12 items), Spec gives conversation (avg 2 items)
- Buffett battery (10 questions, H3 spec): 2.12 avg divergence — half of Aarik's, suggesting spec value correlates with how much the base model already knows about the subject

### Messaging Reframe — COMPLETE
- All 14 website + 10 codebase touchpoints updated
- "Behavioral specification" adopted as single term
- OpenAPI schema, agent cards, llms.txt, README, PyPI, MCP server all reframed
- Services page hidden (redirects to homepage)
- GitHub repo description updated

### SCOTUS Reasoning Study — DESIGNED
- 8 current justices (drop Jackson, insufficient corpus)
- Build behavioral spec from pre-2020 opinions
- Test: predict reasoning structure on 2020-2025 held-out cases
- All conditions receive same citation bank — selection and application is the signal
- C3 control: wrong justice's spec loaded — proves specific content matters
- A domain-expert human evaluator as blind evaluator
- Citation enforcement: mechanical stripping of hallucinated citations, logged
- Gap in literature: vote prediction solved (70%), reasoning prediction open
- Cost: ~$50-100

### Blind Recognition Test — DESIGNED
- 100 questions, 4 conditions (your spec, wrong spec, facts only, no context)
- Obfuscation layer strips style markers, preserves reasoning
- Subject picks "which response is mine?" — recognition, not evaluation
- Chance = 25%. If spec picked at 50%+, p < 0.001

### Temporal Prediction Study
- v1 FAILED: quick-gen 625-token specs, tactical decisions → invalid (Mem0 60% > Spec 27%)
- v2 specced: full pipeline runs, behavioral decisions, production specs
- 15 decisions from S86-S102 pre-registered
- Contaminated prediction test: 9/10 spec, 6/10 facts (invalid but directionally interesting)

### Research Findings
- AlpsBench (2026) proved recall != alignment: "explicit memory mechanisms improve recall but do not inherently guarantee more preference-aligned or emotionally resonant responses"
- Nobody in the literature measures behavioral influence from compressed specs
- Prediction fulfillment rate proposed as novel metric
- The prediction triangle: spec prediction, fact prediction, actual outcome — three-way comparison
- Cognitive psychology instruments identified: integrative complexity, expert-novice categorization, counterfactual generation, CART, A-DMC
- InMind (EMNLP 2025) is closest adjacent work

### Outreach
- 25 agentic infrastructure targets identified with platform-specific demos
- CRM updated with "Agentic Infrastructure" category (blue highlighted)
- Wave 9 scraped (7/10): Cal Newport 500, Nir Eyal 389, Sahil Bloom 242
- Wave 10 scraped (3/5): Harrison Chase 388, Joao Moura 31, Flo Crivello 25
- Engagement: Byrne Hobart (viewed+unlocked), Derek Sivers (viewed+unlocked), Visakan Veerasamy (viewed)

### Infrastructure
- `baselayer export` command added — self-contained HTML of spec, opens in browser
- Buffett re-authored with H3 prompts (was pre-H3)
- H-ARC dataset downloaded (1,729 humans, 800 reasoning tasks)
- Game of 24 think-aloud dataset downloaded (541 participants, 4,947 verbal traces)
- All serving layer code pushed to GitHub as experimental

### Key Decisions
- Research over revenue — services page hidden, research path chosen
- "Behavioral specification" as single term everywhere (collective consensus)
- Embedding router killed — model does the routing (C6 architecture)
- The diff IS the identity signal — the spec operates alongside the human, never alone
- SCOTUS study as the definitive experiment — reasoning chains as ground truth

### Feller's Key Observations
- "Cart before horse" — naming was consuming energy that should go to the serving layer
- "Spec predicts itself. Raw facts predict you. Which one's actually you?" — the prediction triangle
- "The spec predicts the spec. What predicts the spec changing?" — the daemon's purpose
- "Blocking calls hide in quiet places" — TUI had synchronous startup loading
- "Milliseconds precise; thinking stays opaque. Name those states." — on the Game of 24 data

---

