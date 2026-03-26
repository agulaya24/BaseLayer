# Base Layer — Go-to-Market Strategy

**February 2026 · v2**

---

## Overview

Base Layer is a behavioral memory system that extracts facts from your AI conversation history, classifies them by commitment depth, identifies epistemic axioms and behavioral predictions, validates everything through adversarial review, and produces a compressed brief (~2,400 tokens) that makes any AI model understand how you think, decide, and act.

**The core value proposition:** Your AI stops asking who you are. It already knows — not just your name and job title, but that you rebuild from scratch when you hit a wall, that your career decisions filter through family impact, and that you treat unsolicited advice as a status assertion. That understanding persists across every tool and every provider.

**What's been built:** A 12-step pipeline (import → extract → embed → score → classify → tier → contradictions → consolidate → anchors → author layers → collective review → assemble brief) validated across two users with divergent profiles. 3,927 active facts, 9 epistemic axioms, 12 behavioral predictions, 81% combined confidence from four-persona adversarial review. The system is functionally complete. What's missing is packaging, distribution, and market validation beyond n=2.

**The strategic question this document answers:** How does Base Layer go from a working pipeline on one machine to a product that developers install, use, and pay for? And specifically — where should it live?

---

## Validation Status

### What's Proven

**The three-layer architecture works.** Anchors (epistemic axioms), Core (biography + relationships + context), and Predictions (behavioral patterns with trigger → detection → directive structure) produce meaningfully different AI interactions compared to flat-file memory or no memory at all.

**The system differentiates between users.** Aarik and Bavani produce completely different anchors, predictions, and core overviews from the same pipeline. This isn't template-fitting — it's genuine behavioral modeling.

**Bavani was impressed by the epistemic anchors' specificity.** Without extended interaction or explicit self-description, the system identified core beliefs she reasons *from* — not generic personality traits, but specific epistemological commitments. Full write-up pending, but her reaction validates that the anchor extraction captures something real. This matters because it proves the system can surface non-obvious identity structure, not just demographic facts.

**Journal input produces better identity layers per fact than conversation history.** Bavani's 139 journal-derived facts scored higher than Aarik's 3,927 conversation-derived facts. Journal writing is inherently self-reflective — higher signal-to-noise. This finding shapes the onboarding strategy: journal-first, conversation-enriched.

**The Collective catches real problems.** Four-persona adversarial review caught hallucinated physical attributes, wrong pronouns, collapsed prediction dimensions, and axiom-core leakage. Combined confidence went from 44% to 81% in one session through iterative review.

### What's Unproven

**n=2.** Two users, one of whom built the system. Need 3–5 genuinely different profiles: someone non-reflective, someone whose stated beliefs contradict their behavior, someone with minimal conversation history.

**Cold-start onboarding time.** What does "install → functional brief" take? If it's 10 minutes with journal prompts, it's a product. If it's days of pipeline runs, it's a research project.

**Behavioral predictions actually change AI output quality.** The three-layer brief *feels* better in conversation, but there's no controlled A/B test showing measurable improvement in task completion, user satisfaction, or response relevance. This is the biggest validation gap.

**Willingness to pay.** Developers will install a free tool. Whether they'll pay $15–25/month for the full pipeline is an assumption, not data.

---

## The Distribution Question: Where Should Base Layer Live?

The original GTM strategy (v1) positioned Base Layer as an OpenClaw skill — "The memory upgrade for OpenClaw." This section stress-tests that assumption.

### OpenClaw: Honest Assessment

**What OpenClaw offers:**
- 150K+ GitHub stars → concentrated developer community
- Skill system (ClawHub) → built-in distribution channel
- Multi-model routing → perfect use-case alignment
- Local-first ethos → matches Base Layer's values
- The narrative is clean: "The memory upgrade for OpenClaw" is one sentence

**What gives pause:**
- **Founder departure.** OpenClaw's creator joined OpenAI (Feb 14, 2026). The project is moving to an open-source foundation. Foundations can sustain projects (Linux, Kubernetes) or let them stall (many others). Betting primary distribution on a platform in governance transition is risky.
- **The Python → TypeScript rewrite.** The entire Base Layer pipeline is Python + SQLite + ChromaDB + Ollama. OpenClaw skills are TypeScript/Node. That's not a port — it's a rewrite. For a solo founder, this is months of engineering work before shipping anything. The Python pipeline works *today*.
- **Audience ceiling.** OpenClaw's daily active users are estimated at 10–30K. That's the total addressable Day-1 market. Compare: Claude Desktop has millions of users. Cursor has a large and growing developer base. MCP is supported across many tools. The OpenClaw audience is a fraction of the broader multi-model developer audience.
- **Skill ecosystem maturity.** ClawHub is new. If the typical skill has dozens of installs, not thousands, you're launching in a dead mall. Distribution only works if people are actually browsing the channel.
- **Platform coupling.** Positioning *as* an OpenClaw skill means Base Layer's identity is tied to OpenClaw's fate. If OpenClaw's momentum stalls post-founder-departure, Base Layer stalls with it.

**Verdict:** OpenClaw should be a distribution *channel*, not the product *identity*. It's one of several ways to reach users, not the foundation the brand is built on.

### MCP (Model Context Protocol): The Current Moment

MCP is Anthropic's protocol for connecting tools and data sources to AI models. As of February 2026, it's supported by Claude Desktop, Claude Code, Cursor, Windsurf, Cline, and a growing list of developer tools.

**Why MCP matters for Base Layer:**
- **Reach.** The combined user base of MCP-supporting tools is 10–100x larger than OpenClaw's.
- **No rewrite.** An MCP server can be written in Python. The existing pipeline runs as-is behind the MCP interface. Ship in days, not months.
- **Clean integration model.** The MCP server reads your conversation history, runs the pipeline, and serves the behavioral brief as context that gets injected into every conversation. The server runs locally, processes everything locally.
- **Tool-agnostic.** Same MCP server works with Claude Desktop, Claude Code, Cursor, and any future MCP-supporting tool. One integration, many surfaces.
- **Discovery is growing.** MCP server registries and directories are emerging. The protocol is getting significant developer attention.

**Risks:**
- MCP is Anthropic-originated. If other providers don't adopt it, reach stays Claude-ecosystem-only.
- The protocol is evolving. Breaking changes are possible.
- No centralized marketplace equivalent to ClawHub (yet).

**Verdict:** MCP is the strongest Day-1 technical integration. It requires the least engineering work and reaches the largest audience. The main risk (Anthropic-only) is mitigated by the fact that Base Layer's output is model-agnostic — the brief works in any system prompt regardless of how it gets there.

### Open-Source CLI: The Foundation

The simplest possible distribution: `pip install baselayer`. User runs the pipeline locally, gets output files.

**What this looks like:**
```
$ pip install baselayer
$ baselayer import --chatgpt ~/Downloads/conversations.json
$ baselayer import --claude ~/Downloads/claude-export/
$ baselayer build
$ baselayer export --claude-code    # writes CLAUDE.md
$ baselayer export --cursor         # writes .cursorrules
$ baselayer export --system-prompt  # writes brief.txt
```

**Why this matters:**
- **Ships today.** The pipeline is Python. Package it, publish it, done.
- **No platform dependency.** Works regardless of what happens to OpenClaw, MCP, or any other ecosystem.
- **Maximum flexibility.** User decides where the brief goes. CLAUDE.md, .cursorrules, custom system prompt, API integration — the CLI produces the artifact, the user places it.
- **Open-source credibility.** The extraction pipeline, classification system, and brief assembly become inspectable. Developers trust what they can read.

**Limitations:**
- No auto-injection. User has to manually place the output file or configure their tools.
- No continuous learning. The brief is a snapshot, not a live system.
- Requires local Python + dependencies (ChromaDB, embedding model).

**Verdict:** The CLI is the foundation layer (pun intended). It's what you ship first, it's what everything else builds on, and it's what persists if any platform integration breaks. MCP server, OpenClaw skill, and future integrations are all wrappers around this core.

### Recommended Multi-Channel Strategy

**Layer 1 — Foundation (Week 1):** Open-source Python CLI on GitHub + PyPI. `pip install baselayer`. Runs pipeline, exports brief as CLAUDE.md, .cursorrules, or plain text.

**Layer 2 — Integration (Week 2–4):** MCP server that wraps the CLI. Install once, every MCP-supporting tool gets the brief automatically. This is the "it just works" experience.

**Layer 3 — Ecosystem (Month 2–3):** OpenClaw skill that wraps the same core. Reaches OpenClaw users specifically. TypeScript wrapper that shells out to Python if needed — pragmatic over pure.

**Layer 4 — Standalone (Month 4–6):** LiteLLM-based local proxy. Point any tool at localhost:4000, get memory injection. For tools that don't support MCP.

**Layer 5 — Consumer (Month 6+):** Browser extension for claude.ai / chatgpt.com. Only if demand signals are clear. Most maintenance-heavy approach.

This progression means Base Layer is never dependent on any single platform. The CLI is the core. Everything else is a distribution surface.

---

## Getting In Front of People: Distribution Channels

### Tier 1 — Launch Day

| Channel | Action | Why It Works |
|---|---|---|
| **GitHub** | Open-source repo with clear README, install instructions, demo GIF | Developers discover through stars/forks. The repo IS the product page for technical users. |
| **Hacker News** | Show HN: Base Layer — your AI learns how you think, not just what you said | HN audience is exactly the multi-model power user. Technical depth plays well here. |
| **Twitter/X** | Thread: "I built a system that extracted 3,927 facts from my ChatGPT history and turned them into a behavioral model. Here's what happened." | Personal story + technical depth. The numbers are compelling. The fact that it identified epistemic axioms is novel enough to go viral in AI circles. |
| **Reddit** | r/LocalLLaMA (local storage angle), r/ClaudeAI, r/ChatGPTPro, r/MachineLearning | Each community gets a different framing. LocalLLaMA cares about local processing. ClaudeAI cares about Claude integration. MachineLearning cares about the epistemological approach. |

### Tier 2 — Week 2–4

| Channel | Action | Why It Works |
|---|---|---|
| **Technical blog series** | (1) Why AI memory is broken. (2) How we built epistemic anchors. (3) Inside the Collective: adversarial review for identity. (4) The audience principle: writing for machines. | Long-tail SEO. Each post stands alone but drives back to the product. The epistemic anchors post is the most novel — nothing else in the market does this. |
| **YouTube** | 5-minute demo: install → import ChatGPT export → see your behavioral brief → conversation comparison | Video converts differently than text. Show the terminal, show the brief, show the before/after conversation. |
| **OpenClaw Discord** | Announce in #skills and #show-and-tell | Reaches OpenClaw users directly. Lower effort than building a full skill — announce the CLI + MCP server, skill comes later. |

### Tier 3 — Month 2–3

| Channel | Action | Why It Works |
|---|---|---|
| **AI newsletters** | Pitch to Ben's Bites, The Neuron, TLDR AI, AI Breakfast | Newsletter features drive install spikes. The "epistemic anchors" angle is genuinely novel — newsletter editors look for things their audience hasn't seen. |
| **Product Hunt** | Launch when the MCP server + CLI are polished | PH is consumer-facing. Wait until the install experience is smooth. |
| **Podcast appearances** | AI-focused podcasts (Latent Space, Practical AI, The AI Podcast) | Aarik's personal story (built a system to make AI know him, discovered journal input beats conversation history, the Bavani experiment) is a compelling narrative for a 30-minute conversation. |
| **Conference lightning talks** | AI Engineer, local AI/ML meetups | 5-minute talk: "I gave an AI 1,892 of my conversations. It found 9 beliefs I didn't know I had." |

### Content That Drives Organic Discovery

The strongest content angle is the **epistemic anchors story.** No other memory system in the market claims to identify the axioms a person reasons from. This is genuinely novel and worth building a content strategy around.

Post ideas (ready to publish from existing LinkedIn drafts):
1. "Your AI doesn't know you. Here's the proof." — before/after comparison
2. "I fed an AI 1,892 conversations. It found beliefs I didn't know I had." — anchor discovery story
3. "The problem with AI memory isn't storage — it's epistemology." — category-creation piece
4. "My wife used the system for 8 journal entries. It outperformed 1,892 conversations." — journal finding
5. "We built an adversarial review system for AI memory. It caught hallucinated facts about me." — Collective story

Each post stands alone, drives curiosity, and links back to the repo/landing page.

---

## Initial Applications: What Day 1 Looks Like

### Application 1: Personal AI Configuration Generator

The minimum viable product. Upload your ChatGPT export → pipeline runs → get output files → drop them into your tools.

**User experience:**
```
$ baselayer import --chatgpt ~/Downloads/conversations.json
  → Imported 1,847 conversations, 30,408 messages

$ baselayer build
  → Extracted 3,291 facts
  → Classified: 2,400 biographical, 450 preference, 280 positional, 161 behavioral
  → Identified 7 epistemic anchors, 9 behavioral predictions
  → Collective review: 78% combined confidence
  → Brief: 2,218 tokens

$ baselayer export --claude-code
  → Wrote ~/.claude/BASELAYER.md
  → Your next Claude Code session already knows you.
```

**Who it's for:** Any developer with a ChatGPT or Claude export who uses Claude Code or Cursor.

**Time to value:** 10–20 minutes (import + pipeline run on commodity hardware).

### Application 2: Journal-First Onboarding

Based on the Bavani finding (journal > conversation), offer a structured onboarding path for users without extensive conversation history.

**User experience:**
```
$ baselayer onboard
  → Starting guided journal session (5-10 prompts)
  → "Describe a decision you made recently that others disagreed with."
  → "What's something you believe that most people in your field don't?"
  → "When you're stuck on a problem, what's your first instinct?"
  ...

$ baselayer build
  → 47 facts extracted from 8 journal entries
  → 4 epistemic anchors identified
  → Brief: 1,400 tokens, 72% confidence
  → Ready. Enriches automatically as you have more conversations.
```

**Who it's for:** New users, users without ChatGPT exports, anyone who wants a quick start.

**Time to value:** 15 minutes of writing → immediate brief.

### Application 3: MCP Memory Server

For users who want "always-on" memory without manual file management.

**User experience:**
```
$ baselayer serve --mcp
  → MCP server running on localhost:3847
  → Connect in Claude Desktop: Settings → MCP → Add Server → localhost:3847
  → Brief auto-injects into every conversation.
  → New conversations captured for continuous enrichment.
```

**Who it's for:** Claude Desktop power users, Claude Code users who want auto-updating memory.

**Time to value:** 5 minutes after initial pipeline build.

### Application 4: Before/After Conversation Comparison

The single most compelling demo artifact. Same prompt, same model, with and without the behavioral brief.

**Without Base Layer:**
> **You:** Should I take the job offer?
>
> **Claude:** I'd be happy to help you think through this decision! Could you tell me more about the role, your current situation, and what's important to you in your career?

**With Base Layer:**
> **You:** Should I take the job offer?
>
> **Claude:** Given that you tend to evaluate career moves through family impact first and financial upside second, and that you've historically regretted decisions made under time pressure — what's the timeline on this offer, and have you and Bavani talked through the logistics?

The second response demonstrates *understanding*, not just *knowledge*. The model knows the decision framework, the relationship dynamics, and the behavioral pattern (regret under pressure). This before/after is the conversion engine — put it everywhere.

---

## Release Strategy

### Phase 1: Open-Source Foundation (Weeks 1–4)

**Goal:** Get Base Layer on GitHub with a working CLI that developers can install and run.

| Week | Deliverable |
|---|---|
| 1 | Package pipeline as `pip install baselayer`. README with clear install + demo. Push to GitHub + PyPI. |
| 2 | Show HN post. Twitter thread. Reddit posts (LocalLLaMA, ClaudeAI). |
| 3 | MCP server wrapper. Test with Claude Desktop and Claude Code. |
| 4 | Journal onboarding mode. Before/after demo artifacts. First blog post. |

**Success metrics:** 100+ GitHub stars. 50+ CLI installs. 10+ users who complete the full pipeline. 3+ unsolicited before/after comparisons from real users.

### Phase 2: Integration & Validation (Weeks 5–10)

**Goal:** Prove the system works for people who didn't build it. Expand integrations.

| Week | Deliverable |
|---|---|
| 5–6 | Recruit 5 diverse test users from HN/Reddit/OpenClaw. Run full pipeline on each. Collect qualitative feedback. |
| 7–8 | OpenClaw skill (TypeScript wrapper, shells to Python core). Publish to ClawHub. |
| 9–10 | Newsletter pitches. Second blog post (epistemic anchors deep-dive). YouTube demo. |

**Success metrics:** 5 validated user profiles with divergent anchors. Onboarding time under 20 minutes. 3+ users who report measurably different AI interactions.

### Phase 3: Monetize (Weeks 11–16)

**Goal:** Launch Pro tier. Establish revenue.

| Week | Deliverable |
|---|---|
| 11–12 | Pro tier: full Collective review, continuous learning, priority anchor extraction. $15–25/month, BYOK. |
| 13–14 | Product Hunt launch. Podcast pitches. Conference talk submissions. |
| 15–16 | LiteLLM proxy for tool-agnostic injection. Evaluate browser extension demand. |

**Success metrics:** 25+ paying users. $500+ MRR. Net Promoter Score from validated users.

---

## Business Model

### Free Tier (Open Source)

- CLI: import, extract, build, export
- Single-layer brief (facts only, no anchors or predictions)
- Manual export to CLAUDE.md / .cursorrules / text file
- Community-supported

### Pro Tier ($15–25/month)

- Full three-layer architecture (anchors + core + predictions)
- Collective adversarial review (quality validation)
- MCP server with continuous learning
- Cross-provider import processing
- Journal onboarding with guided prompts
- Priority support

Users bring their own API keys for LLM operations. Base Layer charges for the memory layer — the pipeline, the quality system, and the integrations. Same model as Cursor (charges for the tool, not the model).

### Revenue Projections (Conservative, organic only)

| Metric | Month 3 | Month 6 | Month 12 |
|---|---|---|---|
| CLI installs (free) | 300–800 | 1,500–4,000 | 5,000–12,000 |
| Pro conversions (5–8%) | 15–65 | 75–320 | 250–960 |
| MRR @ $20 avg | $300–$1,300 | $1,500–$6,400 | $5,000–$19,200 |

These projections assume no paid acquisition and no viral moment. Upside comes from a compelling Show HN post, newsletter coverage, or the before/after demo being shared organically.

---

## Competitive Landscape

| Competitor | What They Do | Base Layer's Advantage |
|---|---|---|
| **ChatGPT Memory** | Key-value fact storage, locked to OpenAI | Cross-provider. Behavioral model, not fact list. Contradiction detection. |
| **Claude Memory** | Fact extraction, locked to Anthropic | Cross-provider. Epistemic anchors. Adversarial review. |
| **Mem0** | Memory API for developers | User-facing product, not just developer API. Epistemic depth (axioms, commitment levels). |
| **Letta (MemGPT)** | Long-term memory management for agents | Three-layer architecture. Behavioral predictions. Quality gate (Collective). |
| **Zep** | Memory and RAG for AI apps | User-facing. Behavioral modeling, not just retrieval. Local-first. |
| **Custom instructions** | User-written system prompts | Auto-generated from actual behavior. Validated. Evolving. |

**Structural advantage:** No single AI provider will build cross-provider memory. OpenAI won't ingest Claude conversations. Anthropic won't ingest GPT conversations. Only a neutral, user-owned layer can aggregate understanding across all providers. This is a category that can only be built from the outside.

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **n=2 doesn't generalize** | High | Recruit diverse test users early (Week 5). If the system fails on non-reflective users, that's a fundamental architecture problem worth discovering before monetizing. |
| **Onboarding too slow** | High | Journal-first path as alternative. Structured questionnaire that generates initial model in 15 minutes. Gradual enrichment from conversations. |
| **Hardware requirements filter users** | Medium | Extraction can run on API (Sonnet/Haiku) instead of local Ollama. Offer cloud processing option for users without GPUs. Trade privacy purity for accessibility. |
| **Free tier is good enough** | High | Ship free as genuinely useful but visibly limited. The quality gap between single-layer and three-layer should be obvious. Show it, don't just claim it. |
| **LLM providers improve native memory** | Medium | They still can't cross-provider. Their improvement validates the category. Base Layer owns the neutral layer. |
| **MCP protocol changes or stalls** | Low-Medium | CLI is the foundation — MCP is one integration. If MCP stalls, the brief still exports as files. |
| **OpenClaw ecosystem stalls** | Medium | OpenClaw is one channel, not the identity. Pipeline is Python, portable, platform-independent. |
| **Security/privacy backlash** | Medium | Local-only processing is the trust differentiator. Open-source code is auditable. No data ever leaves the user's machine (unless they opt into API-based extraction). |

---

## Open Questions for Decision

1. **API vs. local extraction for the skill.** The current pipeline uses Ollama + Qwen 14B locally (10GB VRAM). Most developers don't have this. Should the packaged product default to API-based extraction (Sonnet/Haiku, ~$1 per full run) with local as an option for privacy purists?

2. **What goes in the free tier?** The current proposal is single-layer (facts only). Alternative: full three-layer but without Collective review (no quality gate). The quality gap is the upsell driver — if the free tier is too good, nobody pays. If it's too limited, nobody installs.

3. **Brand identity.** Is Base Layer "the memory upgrade for OpenClaw" or "the behavioral memory layer for AI"? This document recommends the latter, with OpenClaw as one distribution channel. But the narrower positioning has an advantage: it's easier to explain and easier to win a small market.

4. **Solo vs. team.** Everything in this document is scoped for a solo founder. The 90-day timeline is aggressive for one person, realistic for two. Is there a co-founder or early engineer in the picture?
