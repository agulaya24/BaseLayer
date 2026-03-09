# LLM Provider Cost Comparison for Base Layer Pipeline

**Last updated:** 2026-02-25 (Session 43)
**Purpose:** Evaluate alternative LLM providers for each Base Layer pipeline step to identify cost savings without sacrificing quality.

---

## 1. Raw Pricing Table — All Providers

All prices are **per million tokens (MTok)** in USD. Context windows in thousands (K) or millions (M) of tokens.

### Anthropic (Current Baseline)

| Model | Input | Output | Context | Batch Input | Batch Output | Notes |
|-------|------:|-------:|--------:|------------:|-------------:|-------|
| Claude Haiku 4.5 | $1.00 | $5.00 | 200K | $0.50 | $2.50 | Fastest Claude. Cache reads $0.10/MTok |
| Claude Sonnet 4.6 | $3.00 | $15.00 | 200K (1M beta) | $1.50 | $7.50 | Long context 2x input, 1.5x output >200K |
| Claude Opus 4.6 | $5.00 | $25.00 | 200K (1M beta) | $2.50 | $12.50 | Best reasoning. Fast mode 6x ($30/$150) |
| Claude Haiku 3 (deprecated) | $0.25 | $1.25 | 200K | $0.125 | $0.625 | Still available. Weakest capability |

### OpenAI

| Model | Input | Output | Context | Batch Input | Batch Output | Notes |
|-------|------:|-------:|--------:|------------:|-------------:|-------|
| GPT-4.1-nano | $0.10 | $0.40 | 1M | $0.05 | $0.20 | Cheapest capable. No reasoning step |
| GPT-4o-mini | $0.15 | $0.60 | 128K | $0.075 | $0.30 | Predecessor to 4.1-mini. Still available |
| GPT-4.1-mini | $0.40 | $1.60 | 1M | $0.20 | $0.80 | Matches/exceeds GPT-4o on evals |
| GPT-4o | $2.50 | $10.00 | 128K | $1.25 | $5.00 | Mid-tier workhorse |
| GPT-4.1 | $2.00 | $8.00 | 1M | $1.00 | $4.00 | Latest flagship. 1M native context |
| o3-mini | $1.10 | $4.40 | 200K | $0.55 | $2.20 | Reasoning model. Hidden reasoning tokens billed as output |
| o4-mini | $1.10 | $4.40 | 200K | $0.55 | $2.20 | Latest reasoning model (Apr 2025). Same pricing as o3-mini |

### Google (Gemini API — ai.google.dev)

| Model | Input | Output | Context | Notes |
|-------|------:|-------:|--------:|-------|
| Gemini 2.0 Flash | $0.10 | $0.40 | 1M | Free tier: 15 RPM. Paid: flat pricing all context lengths |
| Gemini 2.5 Flash | $0.15 | $0.60 | 1M | Thinking tokens: $0.30 input / $2.50 output. Best value reasoning |
| Gemini 2.5 Pro | $1.25 | $10.00 | 1M | >200K: $2.50 input / $16.00 output. Best Gemini quality |
| Gemini 1.5 Pro | $1.25 | $5.00 | 2M | >128K: $2.50 input / $10.00 output. Largest context window |

> **Google free tier:** Gemini 2.0 Flash and 2.5 Flash have generous free tiers (15 RPM, 1M TPM, 1,500 RPD). Could handle low-volume pipeline steps at zero cost.

### DeepSeek

| Model | Input | Output | Context | Notes |
|-------|------:|-------:|--------:|-------|
| DeepSeek V3 | $0.14 | $0.28 | 164K | Cache hits: $0.028/MTok. Off-peak 50% discount |
| DeepSeek V3.1 | $0.15 | $0.75 | 128K | Terminus variant: $0.21/$0.79 with 164K context |
| DeepSeek R1 | $0.55 | $2.19 | 164K | Reasoning model. Off-peak 75% discount |

> **DeepSeek caveats:** Chinese provider. Data may route through China. Periodic availability issues reported. Rate limits can be restrictive. Off-peak discounts only during 16:30-00:30 GMT.

### Mistral

| Model | Input | Output | Context | Notes |
|-------|------:|-------:|--------:|-------|
| Mistral Small | $0.20 | $0.60 | 32K | Budget option. Limited context |
| Mistral Medium 3 | $0.40 | $2.00 | 131K | Released May 2025. Good mid-tier |
| Mistral Large 3 | $2.00 | $6.00 | 128K | Flagship. Strong structured output |

> **Mistral caveats:** EU-hosted (good for GDPR). Smaller context windows than competitors. Less proven for structured JSON extraction at scale.

---

## 2. Pipeline Cost Comparison

### Cost Per Conversation Estimates

Assumptions for a typical Base Layer conversation:
- **Average conversation:** ~4,000 input tokens (conversation text + system prompt), ~800 output tokens (extracted JSON)
- **Classification:** ~1,500 input tokens per fact, ~200 output tokens
- **Tier reclassification:** ~2,000 input tokens per fact, ~300 output tokens
- **Layer authoring:** ~8,000 input tokens (facts + prompt), ~2,000 output tokens per layer
- **Collective review:** ~12,000 input tokens (layer + review prompt), ~3,000 output tokens per review cycle

### Step-by-Step Comparison

#### EXTRACT (High volume — ~1,000 conversations)
*Needs: JSON reliability, entity resolution, follows complex extraction prompt*

| Provider/Model | Input Cost | Output Cost | Cost/Convo | Cost/1,000 | vs. Current |
|----------------|----------:|----------:|----------:|----------:|----------:|
| **Haiku 4.5 (current)** | $1.00 | $5.00 | $0.008 | **$8.00** | baseline |
| GPT-4.1-nano | $0.10 | $0.40 | $0.0007 | **$0.72** | -91% |
| GPT-4o-mini | $0.15 | $0.60 | $0.001 | **$1.08** | -87% |
| GPT-4.1-mini | $0.40 | $1.60 | $0.003 | **$2.88** | -64% |
| Gemini 2.0 Flash | $0.10 | $0.40 | $0.0007 | **$0.72** | -91% |
| DeepSeek V3 | $0.14 | $0.28 | $0.0008 | **$0.78** | -90% |
| Mistral Small | $0.20 | $0.60 | $0.001 | **$1.28** | -84% |

> **Extraction verdict:** Haiku 4.5 at $1.00/$5.00 is expensive for extraction. GPT-4.1-nano and Gemini 2.0 Flash are 10x cheaper. The question is whether they can follow the extraction prompt reliably and produce valid JSON.

#### CLASSIFY (Medium volume — ~4,000 facts)
*Needs: Accurate fact_type and commitment_depth classification*

| Provider/Model | Input Cost | Output Cost | Cost/Fact | Cost/4,000 | vs. Current |
|----------------|----------:|----------:|----------:|----------:|----------:|
| **Haiku 4.5 (current)** | $1.00 | $5.00 | $0.0025 | **$10.00** | baseline |
| GPT-4.1-nano | $0.10 | $0.40 | $0.00023 | **$0.93** | -91% |
| GPT-4o-mini | $0.15 | $0.60 | $0.00035 | **$1.40** | -86% |
| GPT-4.1-mini | $0.40 | $1.60 | $0.00092 | **$3.68** | -63% |
| Gemini 2.0 Flash | $0.10 | $0.40 | $0.00023 | **$0.93** | -91% |
| DeepSeek V3 | $0.14 | $0.28 | $0.00027 | **$1.06** | -89% |

> **Classification verdict:** Same story. Current 91%/94% accuracy was achieved with Haiku — cheaper models need accuracy testing before switching.

#### TIER (Medium volume — ~4,000 facts)
*Needs: Judgment quality to distinguish context/situational/identity*

| Provider/Model | Input Cost | Output Cost | Cost/Fact | Cost/4,000 | vs. Current |
|----------------|----------:|----------:|----------:|----------:|----------:|
| **Sonnet 4.6 (current)** | $3.00 | $15.00 | $0.011 | **$42.00** | baseline |
| Haiku 4.5 | $1.00 | $5.00 | $0.003 | **$11.50** | -73% |
| GPT-4.1-mini | $0.40 | $1.60 | $0.001 | **$4.08** | -90% |
| GPT-4.1 | $2.00 | $8.00 | $0.006 | **$26.40** | -37% |
| Gemini 2.5 Flash | $0.15 | $0.60 | $0.0004 | **$1.50** | -96% |
| Gemini 2.5 Pro | $1.25 | $10.00 | $0.006 | **$22.50** | -46% |
| Mistral Medium 3 | $0.40 | $2.00 | $0.001 | **$5.40** | -87% |

> **Tier verdict:** Sonnet at $3/$15 is the most expensive step per-fact. Gemini 2.5 Flash with thinking capability could be a strong contender at 96% less cost. Needs judgment quality eval.

#### AUTHOR LAYERS (Low volume — 3 layers)
*Needs: Highest narrative quality. This is user-facing identity text.*

| Provider/Model | Input Cost | Output Cost | Cost/Layer | Cost/3 Layers | vs. Current |
|----------------|----------:|----------:|----------:|----------:|----------:|
| **Sonnet 4.6 (current)** | $3.00 | $15.00 | $0.054 | **$0.16** | baseline |
| GPT-4.1 | $2.00 | $8.00 | $0.032 | **$0.10** | -40% |
| Gemini 2.5 Pro | $1.25 | $10.00 | $0.030 | **$0.09** | -44% |
| Opus 4.6 | $5.00 | $25.00 | $0.090 | **$0.27** | +69% |

> **Author verdict:** At ~$0.05-0.10 per layer, cost is negligible regardless of provider. Optimize for quality, not cost. Sonnet is fine.

#### COLLECTIVE REVIEW (Low volume — 3 layers x 1-3 iterations)
*Needs: Best available judgment. Four-persona review requiring nuance.*

| Provider/Model | Input Cost | Output Cost | Cost/Review | Cost/Full Review (9 cycles) | vs. Current |
|----------------|----------:|----------:|----------:|----------:|----------:|
| **Opus 4.6 (current)** | $5.00 | $25.00 | $0.14 | **$1.22** | baseline |
| GPT-4.1 | $2.00 | $8.00 | $0.048 | **$0.43** | -65% |
| Gemini 2.5 Pro | $1.25 | $10.00 | $0.045 | **$0.41** | -67% |
| Sonnet 4.6 | $3.00 | $15.00 | $0.081 | **$0.73** | -40% |

> **Review verdict:** Opus is justified here — this is the quality gate. But at $1.22 for the full review pipeline, cost is not a real concern. Keep Opus.

#### CONTRADICTIONS (Medium volume — pairwise checks on ~4,000 facts)
*Needs: Nuanced semantic judgment. Currently manual/unbuilt.*

| Provider/Model | Input Cost | Output Cost | Cost/Check | Notes |
|----------------|----------:|----------:|----------:|-------|
| Opus 4.6 | $5.00 | $25.00 | $0.015 | Best judgment, expensive at scale |
| Sonnet 4.6 | $3.00 | $15.00 | $0.008 | Good balance |
| GPT-4.1 | $2.00 | $8.00 | $0.005 | Competitive quality, lower cost |
| Gemini 2.5 Pro | $1.25 | $10.00 | $0.004 | Strong reasoning |
| GPT-4.1-mini | $0.40 | $1.60 | $0.001 | Pre-filter candidate pairs only |

> **Contradictions verdict:** Two-stage approach recommended. Cheap model (GPT-4.1-mini or Gemini Flash) for candidate pair identification via embeddings + similarity. Sonnet/GPT-4.1 for final judgment on flagged pairs.

---

## 3. Total Cost Per 1,000 Conversations — Full Pipeline

Assumptions: 1,000 conversations yielding ~4,000 facts, 3 identity layers, 1 full collective review cycle.

| Pipeline Step | Anthropic (Current) | OpenAI (Best Value) | Google (Best Value) | DeepSeek |
|---------------|-------------------:|-------------------:|-------------------:|-------------------:|
| Extract (1,000 convos) | $8.00 (Haiku 4.5) | $0.72 (4.1-nano) | $0.72 (2.0 Flash) | $0.78 (V3) |
| Classify (4,000 facts) | $10.00 (Haiku 4.5) | $0.93 (4.1-nano) | $0.93 (2.0 Flash) | $1.06 (V3) |
| Tier (4,000 facts) | $42.00 (Sonnet 4.6) | $4.08 (4.1-mini) | $1.50 (2.5 Flash) | $5.40 (V3.1) |
| Author (3 layers) | $0.16 (Sonnet 4.6) | $0.10 (4.1) | $0.09 (2.5 Pro) | N/A |
| Review (9 cycles) | $1.22 (Opus 4.6) | $0.43 (4.1) | $0.41 (2.5 Pro) | N/A |
| Contradictions (est.) | $4.00 (Sonnet 4.6) | $1.50 (4.1-mini) | $0.60 (2.5 Flash) | $1.00 (V3) |
| **TOTAL** | **$65.38** | **$7.76** | **$4.25** | **$8.24** |
| **vs. Current** | baseline | **-88%** | **-93%** | **-87%** |

> **Important caveats on the totals above:**
> - These assume equivalent quality at each step. Quality MUST be validated before switching.
> - The current Anthropic cost is dominated by Tier ($42) because Sonnet is expensive for 4,000 classification-style calls. This is the highest-leverage optimization target.
> - Author and Review costs are negligible (<$2 combined) regardless of provider. Optimize these for quality, not cost.
> - DeepSeek is marked N/A for Author/Review because identity-layer quality is too important to risk on a less-proven provider with availability concerns.

### Batch API Savings (Anthropic-Only Optimization)

If staying with Anthropic, batch processing offers 50% off:

| Step | Standard | Batch | Savings |
|------|--------:|------:|--------:|
| Extract (Haiku 4.5) | $8.00 | $4.00 | $4.00 |
| Classify (Haiku 4.5) | $10.00 | $5.00 | $5.00 |
| Tier (Sonnet 4.6) | $42.00 | $21.00 | $21.00 |
| **TOTAL** | **$60.00** | **$30.00** | **$30.00 saved** |

> Batch API is the easiest optimization — no code changes beyond switching to async batch calls. Cuts cost in half with zero quality risk.

---

## 4. Recommendations

### Immediate (No quality testing needed)

1. **Switch to Anthropic Batch API** for Extract, Classify, and Tier steps. 50% savings, zero quality risk. Current cost ~$60 drops to ~$30 per 1,000 conversations.

2. **Use prompt caching** for Extract and Classify. The system prompt + extraction instructions are identical across all conversations. Cache reads at $0.10/MTok (Haiku) vs $1.00/MTok base = 90% savings on the static portion.

### Short-term (Needs quality testing)

3. **Test Gemini 2.0 Flash for Extract.** At $0.10/$0.40 per MTok, it is 10x cheaper than Haiku 4.5. Run on 50 conversations, compare extraction quality (fact count, JSON validity, entity resolution accuracy). If quality holds, this drops extraction from $8 to $0.72.

4. **Test GPT-4.1-nano for Extract.** Same price tier as Gemini Flash ($0.10/$0.40). Run the same 50-conversation eval. Compare head-to-head with Gemini Flash.

5. **Test Gemini 2.5 Flash for Tier.** At $0.15/$0.60 per MTok with thinking capability, this could replace Sonnet for tier classification at 96% less cost. This is the single highest-leverage test — Tier is 64% of total pipeline cost. Run on 200 facts, compare tier accuracy against Sonnet baseline.

6. **Test GPT-4.1-mini for Classify.** At $0.40/$1.60, it is 75% cheaper than Haiku 4.5 while reportedly matching GPT-4o quality. Run classification eval on 200 facts.

### Medium-term (After quality validated)

7. **Multi-provider pipeline.** Best-of-breed per step:
   - Extract: Gemini 2.0 Flash or GPT-4.1-nano (~$0.72/1K convos)
   - Classify: GPT-4.1-nano or Gemini 2.0 Flash (~$0.93/4K facts)
   - Tier: Gemini 2.5 Flash (~$1.50/4K facts)
   - Author: Sonnet 4.6 (keep — cost negligible, quality critical)
   - Review: Opus 4.6 (keep — cost negligible, quality critical)
   - Contradictions: Two-stage with cheap pre-filter + Sonnet judgment

   **Projected total: ~$5-8 per 1,000 conversations** (vs. $65 current)

### What NOT to do

- **Do not switch Author or Review models to save money.** Combined cost is <$2. Quality is everything here.
- **Do not use DeepSeek for identity-sensitive steps.** Data sovereignty concern — conversations route through Chinese infrastructure. Extraction-only if used at all.
- **Do not use Mistral for extraction.** 32K context on Small is too limiting. Medium/Large context is adequate but pricing is not competitive enough to justify the integration work.
- **Do not switch providers without running the eval.** The 91%/94% classification accuracy baseline exists for a reason. Cheaper is only better if accuracy holds.

---

## 5. Testing Priority Matrix

| Priority | Test | Model | Step | Expected Savings | Effort |
|----------|------|-------|------|-----------------|--------|
| 1 | Gemini 2.5 Flash for Tier | gemini-2.5-flash | Tier | $40/1K convos | Medium — new API integration |
| 2 | Batch API (Anthropic) | Same models | All bulk steps | $30/1K convos | Low — SDK supports it |
| 3 | Gemini 2.0 Flash for Extract | gemini-2.0-flash | Extract | $7/1K convos | Medium — new API integration |
| 4 | GPT-4.1-nano for Extract | gpt-4.1-nano | Extract | $7/1K convos | Medium — new API integration |
| 5 | Prompt caching (Anthropic) | Same models | Extract/Classify | $5-10/1K convos | Low — add cache headers |
| 6 | GPT-4.1-mini for Classify | gpt-4.1-mini | Classify | $8/1K convos | Medium — new API integration |

---

## 6. Provider API Access Notes

### Anthropic
- Tier-based rate limits. Tier 1 starts at 50 RPM for Haiku
- Batch API: 50% discount, results within 24 hours
- Prompt caching: 5-min or 1-hour TTL, 90% read discount
- 1M context: Beta, tier 4+ only

### OpenAI
- GPT-4.1 family: 1M context native, no beta gate
- Batch API: 50% discount available
- Structured outputs (JSON mode): Built-in for 4.1 family — good for extraction
- Rate limits vary by tier and model

### Google
- Free tier on Gemini Flash models: 15 RPM, 1,500 RPD, 1M TPM
- Paid tier: 2,000 RPM for Flash, 1,000 RPM for Pro
- Batch API: 50% discount
- Context caching: Up to 90% savings on repeated prefixes

### DeepSeek
- Off-peak discounts: V3 50% off, R1 75% off (16:30-00:30 GMT)
- Automatic context caching: 90% savings on cache hits
- Rate limits can be restrictive during peak hours
- Data routes through China — not suitable for identity data

### Mistral
- EU-hosted (Paris) — good for GDPR compliance
- Smaller context windows (32K-131K) limit usefulness for long conversations
- La Plateforme API is straightforward
- Less competitive pricing than Google/OpenAI for comparable quality

---

## Sources

- [Anthropic Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [OpenAI Pricing](https://openai.com/api/pricing/)
- [OpenAI Platform Pricing](https://platform.openai.com/docs/pricing)
- [Google Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [DeepSeek Pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [Mistral Pricing](https://mistral.ai/pricing)
- [PricePerToken — OpenAI](https://pricepertoken.com/pricing-page/provider/openai)
- [PricePerToken — DeepSeek](https://pricepertoken.com/pricing-page/provider/deepseek)
- [PricePerToken — Mistral](https://pricepertoken.com/pricing-page/provider/mistral-ai)
- [CostGoat — Claude API](https://costgoat.com/pricing/claude-api)
- [CostGoat — Gemini API](https://costgoat.com/pricing/gemini-api)
- [Artificial Analysis — Gemini 2.5 Flash](https://artificialanalysis.ai/models/gemini-2-5-flash)
