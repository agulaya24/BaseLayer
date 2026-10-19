# Roadmap

This document tracks committed and exploratory work on Base Layer. Dates indicate target windows, not commitments.

## Current state

Pre-1.0. Pipeline is functional end-to-end (one-command `baselayer run`); MCP server is shipping; behavioral specifications generate consistently across 14 historical subjects and original-author corpora; `baselayer verify` audits the provenance of the static layers; `baselayer verify-spec` checks a finished specification against its corpus, and `baselayer consolidate` builds a trigger index from one. The cited path (distill, assemble, author-from-package) is experimental.

## Near-term (next 1-2 quarters)

### Not yet in the public package

The README's limits refer to these; the measured cited builds in its cost table used the support filter from scripts outside the package.

- **Support filter.** Judges each fact against its own quoted words as supported, stretch or not supported before distillation. Today `distill --exclude-ids` takes its list of excluded facts from outside.
- **Stretch sort.** Sorts stretch facts by kind (generalised, added detail, reported, truncation), each kind with its own check.
- **Claim back-check.** Separate research judges check each claim's scope and its reliance on stretch facts. Today `verify-spec --backcheck-results` reads results produced outside the package.
- **Fire-rate measurement for the always-on set.** `consolidate` can choose always-on claims by measured fire rate, but the measurement itself is not in the package.
- **Serving a cited build to an agent.** `consolidate` writes `served.txt` and `index.json`; nothing serves them over MCP yet, so they go into a system prompt by hand.
- **One command for the cited build.** Today it is eight commands ([docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end)).
- **Base Layer Live.** Keeps a specification updated and served as corrections arrive. In development.

### Known defect

- **Traceability embedding check.** When fewer than 90% of facts have vectors, the `baselayer run` traceability step runs `baselayer embed`, which embeds messages, not facts, so the missing fact vectors stay missing and vector provenance skips those facts.

### Production readiness

- **Identity-to-specification refactor.** Code, file paths, and API endpoints still use the legacy `identity` term while documentation has moved to `specification`. The refactor brings code in line with the new positioning. The plan is kept in the maintainer's private working copy, not in this repository. Includes a backwards-compatibility shim for the API.
- **Stable 1.0 API surface.** Lock the CLI command set, MCP tool signatures, and HTTP endpoint shapes. Versioned changelog from this point forward.

### Local pipeline

- **32B-class local models for authoring and composition.** Extraction can already run locally via Ollama (`BASELAYER_EXTRACTION_BACKEND=ollama`; the configured model is `qwen2.5:14b`, `LLM_MODEL` in `config.py`). A 14B local model failed at writing ([D-030](docs/core/DECISIONS.md#d-030-model-role-separation--qwen-extracts-claude-writes)); whether 32B-class local models reach quality parity with Sonnet/Opus is untested. If they do, the project ships a fully-local mode.
- **Structured output enforcement.** Ollama native JSON schema constraints for guaranteed valid extraction output.

### Evaluation

- **Differentiated scoring rubric.** Separate interpretation-heavy questions from literal-recall questions during evaluation, and score epistemic honesty as its own dimension. Current single-rubric scoring conflates these.
- **Faithfulness as a measurement axis.** Operationalize structural faithfulness as its own metric, distinct from compactness and predictive accuracy. Stress-test compressed specifications against the structural patterns that distinguish a person's reasoning.
- **Per-component ablation.** Anchors / Core / Predictions / individual predicates. Identify which structural feature of the specification is doing the work.

## Mid-term (next 2-4 quarters)

### Serving layer

- **Dynamic routing.** A serving system that routes between memory-system retrieval and specification interpretation based on question type. Currently the specification layered on top of retrieval covers most of the gap, but the architectural step of question-class routing has not been built.
- **Streaming specification updates.** Today the specification is a snapshot. Mid-term: detect phase transitions in the source corpus and update specific layers without regenerating from scratch.

### Adoption surface

- **Per-subject spec cards.** Inspired by Hugging Face model cards. Each shipped specification ships with a spec card documenting source corpus, extraction model, validation score, known limitations, and temporal scope.
- **Local examples directory.** Runnable examples under `examples/` with input corpora and expected output specifications. Today `examples/` holds the output specifications for 8 subjects (one with checkable citations) but not their input corpora.
- **Source-type adapters.** Today: ChatGPT, Claude (web and Claude Code), journals, text files and directories, shell history, meeting transcripts. Wanted: Slack exports, Discord exports, longform email archives, voice transcripts.

## Longer-term (research horizons)

### Temporal modeling

- **Time-aware specifications.** Event vs state classification, contradiction detection over time, mention-velocity tracking. The current specification is a point-in-time cross-section; longer-term, capture how a specific person is changing.
- **Phase-transition detection.** Already exists in research tooling; not in production. Promote when the eval rubric supports temporal evaluation.

### Distillation and cost

- **Fine-tuned extraction models.** Train 3B-14B models on Haiku extraction output. Reduce cost to near-zero for high-volume use.

### Composition and orchestration

- **Preference layer separation.** Preference facts (values, prefers, avoids, dislikes, enjoys) are already extracted. Separate display and use case from behavioral specification. Treat preferences and behavioral patterns as distinct layers a consuming agent can compose.
- **Retrieval interaction modeling.** Foundational work in cognitive science studies how memory and interpretation compose in human reasoning, but this has not been applied to human-AI interaction. Mid-to-long term: an operational framework for which kinds of questions need retrieval, interpretation, or both.

## Open questions

Questions the public docs already state as open. None has an answer yet.

- **Is a specification faithful to the person?** No mechanical check establishes it; a specification another model can tell apart from others is distinguishable, not shown to be faithful. Only the person can confirm it ([README](README.md#how-to-check-it), [DEFINITIONS.md](docs/DEFINITIONS.md) D39).
- **Is the difference between specifications more than tone and length?** A simple classifier named the right specification far more often from the reasoning than from the decision, but differences of tone and length were not ruled out ([README](README.md#research)).
- **Which part of the specification does the work?** Anchors, core, predictions or individual predicates (per-component ablation, above).
- **How is the person changing?** Claims are not dated, so a specification is a point-in-time cross-section ([README](README.md#limits-and-what-is-not-included-yet); temporal modeling, above).
- **Is a cheaper leaf model good enough?** Claude Sonnet 5.5 cost a little over a third as much per leaf on a sample, but a blind comparison did not show its leaves as good, and its repair rate is untested ([docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end)).

## Out of scope

Items deliberately not on the roadmap:

- **Hosted SaaS.** Base Layer is a local-first tool plus the served examples on `base-layer.ai`. No hosted multi-tenant deployment is planned.
- **Account systems.** No user accounts, no authentication for personal use, and no usage data collected by Base Layer. Specifications stay local. (ChromaDB, a dependency, has its own anonymized telemetry setting; see the README's Privacy section.)
- **Cross-user behavioral aggregation.** The project is per-user calibration. Aggregate cohort modeling is not the design target.

## How to suggest additions

Open an issue with the label `roadmap` and a one-paragraph description of the proposed item plus its rationale relative to the project's positioning (interpretive layer above memory). Issues are reviewed before being added to this document.
