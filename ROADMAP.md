# Roadmap

This document tracks committed and exploratory work on Base Layer. Dates indicate target windows, not commitments.

## Current state

Pre-1.0. Pipeline is functional end-to-end (one-command `baselayer run`); MCP server is shipping; behavioral specifications generate consistently across 14 historical subjects and original-author corpora; provenance verifier covers four checks against the citation graph.

## Near-term (next 1-2 quarters)

### Production readiness

- **Identity-to-specification refactor.** Code, file paths, and API endpoints still use the legacy `identity` term while documentation has moved to `specification`. The refactor brings code in line with the new positioning. See [`docs/internal/identity_to_specification_refactor_plan.md`](docs/internal/identity_to_specification_refactor_plan.md). Includes a backwards-compatibility shim for the API.
- **`brief_v4.md` rename.** Output filename becomes `specification.md`. Currently flagged as tech debt in `docs/core/ARCHITECTURE.md`.
- **Stable 1.0 API surface.** Lock the CLI command set, MCP tool signatures, and HTTP endpoint shapes. Versioned changelog from this point forward.

### Local pipeline

- **32B-class local models for authoring and composition.** Extraction already runs locally via Ollama (Qwen 3, Gemma 3, Mistral 7B tested). Active research is on whether 32B-class local models produce specifications at quality parity with Sonnet/Opus. If yes, the project ships a fully-local mode by default.
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
- **Local examples directory.** Runnable examples under `examples/` with input corpora and expected output specifications. Today the `examples/` link points to live web examples; reviewers flagged that local files would help adopters.
- **Source-type adapters.** Today: ChatGPT, Claude, journals, text files, directories. Wanted: Slack exports, Discord exports, longform email archives, voice transcripts.

## Longer-term (research horizons)

### Temporal modeling

- **Time-aware specifications.** Event vs state classification, contradiction detection over time, mention-velocity tracking. The current specification is a point-in-time cross-section; longer-term, capture how a specific person is changing.
- **Phase-transition detection.** Already exists in research tooling; not in production. Promote when the eval rubric supports temporal evaluation.

### Distillation and cost

- **Fine-tuned extraction models.** Train 3B-14B models on Haiku extraction output. Reduce cost to near-zero for high-volume use.
- **Anthropic Batch API.** 50% cost savings via batched extraction. Infrastructure built; integration pending.

### Composition and orchestration

- **Preference layer separation.** 822 preference facts (values, prefers, avoids, dislikes, enjoys) already extracted. Separate display and use case from behavioral specification. Treat preferences and behavioral patterns as distinct layers a consuming agent can compose.
- **Retrieval interaction modeling.** Foundational work in cognitive science studies how memory and interpretation compose in human reasoning, but this has not been applied to human-AI interaction. Mid-to-long term: an operational framework for which kinds of questions need retrieval, interpretation, or both.

## Out of scope

Items deliberately not on the roadmap:

- **Hosted SaaS.** Base Layer is a local-first tool plus the served examples on `base-layer.ai`. No hosted multi-tenant deployment is planned.
- **Account systems.** No user accounts, no authentication for personal use, no telemetry. Specifications stay local.
- **Cross-user behavioral aggregation.** The project is per-user calibration. Aggregate cohort modeling is not the design target.

## How to suggest additions

Open an issue with the label `roadmap` and a one-paragraph description of the proposed item plus its rationale relative to the project's positioning (interpretive layer above memory). Issues are reviewed before being added to this document.
