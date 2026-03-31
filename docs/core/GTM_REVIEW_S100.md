# GTM Review — Session 100 (2026-03-30)

**Reviewer:** Claude Opus 4.6 at Aarik's request
**Scope:** base-layer.ai website, messaging, competitive positioning, conversion funnel, outreach strategy
**Method:** Full read of Hero, Nav, Footer, Vision, Try-It, Thoughts, Research page, Waitlist, Journey page wrapper, and COMPARABLES.md

---

## Website Assessment

### First Impression (10-Second Test)
The hero headline — "Other tools store facts. Base Layer models how you think." — lands immediately. It draws a clear competitive line and positions Base Layer as categorically different. The subtext ("How you reason. What you avoid. When your patterns break.") reinforces this with concrete language rather than marketing abstractions.

**Verdict: The value proposition is clear within 10 seconds.** A visitor knows this is about behavioral modeling, not fact storage, and that it produces an "operating guide" for AI. The tooltip on "operating guide" is a smart detail — it answers the obvious follow-up without cluttering the hero.

The "Own your identity." tagline + Apache 2.0 badge signal open-source ownership immediately. Good.

**One weakness:** The hero carousel (Facts vs. Identity Model) is strong for someone who pauses to study it, but it auto-rotates at 10s and the cards are information-dense. A first-time visitor may not absorb what makes the right-side "behavior" card different from the left-side "facts" card without stopping. The concept is excellent — showing the transformation from raw facts to behavioral predictions — but the visual hierarchy could make the contrast more obvious at a glance (e.g., a bigger label like "What others do" vs. "What Base Layer does").

### Navigation
**Easy to find:** Research, Examples, Try It, GitHub, Vision, Journey. Six links plus logo home. Clean, not overcrowded.

**Accent treatment:** "Try It" is the only accent-colored nav link — draws the eye correctly.

**Hidden or underexposed:**
- **Thoughts** is only in the footer under "Connect." Not in the main nav. This is probably fine given there's only one post, but if it grows, it should be promoted.
- **Thinkers pages** (the 29 live subjects) have no discoverable nav path from the public site. A visitor cannot find Scott Alexander's or Kevin Kelly's page unless they have the direct URL. The footer lists only the historical examples (Franklin, Douglass, etc.). This means the strongest social proof asset — real living thinkers with identity models — is invisible to organic visitors.
- **"Follow Updates" / Waitlist** is buried in the footer. The homepage has a waitlist section, but the nav doesn't link to it directly.

### Research Page
Accessible from the nav. Metadata description references "pipeline ablation, prompt ablation, Twin-2K benchmark, BCB evaluation" — this is the right level of specificity for SEO, though it assumes familiarity with the project's vocabulary. For a new visitor, "Twin-2K benchmark" means nothing. For the target audience (technical AI researchers, builders), it signals rigor.

**Assessment:** The research page serves the right audience. It should not be dumbed down. But it would benefit from a one-sentence plain-English summary at the top: "We test whether behavioral compression actually works. Here's what we've found."

### Try-It Page
This is the strongest conversion page on the site. It does several things well:

1. **Two-step flow** — Download zip, paste a prompt into your AI agent. Minimal friction for the technically capable audience.
2. **Agent-first framing** — "Works with any agent that has terminal access: Claude Code, Cursor, Windsurf, Cline, Aider, GitHub Copilot, Warp." This correctly positions Base Layer as tool-agnostic.
3. **Copy-paste prompt** — "Install Base Layer from the zip I downloaded, find my ChatGPT export, and run the pipeline. Show me the cost estimate first." This is genuinely clever. It turns the user's AI agent into the installer.
4. **Cost table** — Real costs from real runs ($0.10 for journals to $1.50 for dense corpora). Transparent, builds trust.
5. **"Where to use your brief"** — Expandable cards for Claude, ChatGPT, Claude Code/Cursor, Claude Desktop, Any System Prompt. Practical and thorough.
6. **Hosted version interest capture** — "We're exploring a hosted version... Drop your email if you'd want that." Smart demand signal collection.
7. **Privacy note** — Clear statement that data stays local.

**Weakness:** The page assumes the visitor already wants to try it. There's no re-statement of the value proposition at the top of Try-It. Someone who lands on /try-it from an external link (Reddit, HN) sees "Build Your Own" and "Import any text. Get an identity model." — but no explanation of WHY they'd want an identity model. A single sentence linking back to the value prop would help: "An identity model teaches AI how you think, decide, and react — so every AI tool you use works with you, not just for you."

### Thoughts Page
Currently one post ("An agent trained during the development of your system, to serve as a daemon after."). The writing is strong — it introduces a genuine conceptual distinction (apprenticeship vs. compression, daemon vs. brief) that advances the project's intellectual framing.

**Assessment:** It adds, not distracts. The risk is that one post looks like an abandoned blog. Either commit to posting regularly (even short observations) or keep it hidden until there are 3-5 posts. One post sitting alone since 2026-03-30 will look stale by April.

### Examples (Franklin, Douglass, Wollstonecraft, Roosevelt, Buffett)
The hero carousel showcases these well. Each example demonstrates a different aspect of behavioral modeling:
- Franklin: Mode detection and switching
- Douglass: Trigger-response patterns
- Wollstonecraft: Conviction-over-courtesy
- Roosevelt: Operating modes (crisis vs. reform)
- Buffett: Decision triggers

**This is the single most effective element on the site.** It shows, rather than tells, what behavioral compression produces. The false-positive guards are particularly compelling — they signal epistemic humility ("here's when this prediction should NOT be applied"), which is the opposite of what most AI tools do.

**The provenance traces** (fact IDs, similarity scores) at the bottom of each card add credibility for technical visitors without cluttering the experience for non-technical ones.

**What's missing:** The examples are all historical figures or public investors. There's no example of a "normal person" — someone whose identity model was built from ChatGPT conversations or journal entries. The thinkers pages (Scott Alexander, Kevin Kelly, etc.) would serve this purpose, but they're gated and undiscoverable. Consider adding one anonymized "personal conversations" example to show the product works on everyday input, not just famous autobiographies.

---

## Messaging

### "Behavioral compression for AI identity"
This is the technical descriptor, not the pitch. It works for the tagline/subtitle position (which is where it appears, via the Logo component's tagline). It does NOT work as a lead message — too abstract, requires unpacking.

### "Other tools store facts. Base Layer models how you think."
**This is the actual pitch, and it's strong.** It positions against the entire competitive landscape in one sentence. "How you think" is the right level of abstraction — specific enough to be meaningful, broad enough to encompass the full product.

### "How someone reasons IS identity"
This is the philosophical thesis, not a marketing message. It belongs on the Vision page (where the argument is made at length). It should not replace "models how you think" on the homepage.

### "Own your identity."
Appears as the accent-colored CTA line on the hero. Good — it encapsulates the sovereignty argument in three words. But it could be misread as a generic privacy slogan. Consider whether "Own your identity model" or "Own how AI sees you" is clearer.

### Elevator Pitch
The elevator pitch is effectively on the website, distributed across the hero: "Base Layer extracts how you reason, what you avoid, and when your patterns break from your conversations and writing, compresses it into a 3-6K token operating guide, and gives it to any AI so it works with you, not just for you. Open source, locally owned, auditable."

That's a good pitch. The problem is it's never stated as a single coherent paragraph anywhere. The Vision page comes closest but is a 2,000-word essay. Consider adding a "What is Base Layer?" one-paragraph section somewhere prominent — possibly the first section below the hero fold.

---

## Competitive Positioning

### vs Mem0 (fact storage, no compression)
**Communicated:** The hero headline ("Other tools store facts") directly addresses this. The COMPARABLES doc nails the technical argument (25% accuracy at 6-fact retrieval = RAG ceiling). **Not on the website though.** The technical competitive comparison exists only in internal docs.

### vs Zep (session memory, no identity)
**Not mentioned anywhere on the site.** Zep isn't even in the COMPARABLES doc. This is fine — Zep is a less relevant competitor than Mem0 or Letta.

### vs Letta (memory blocks, no behavioral modeling)
**Not communicated on site.** The 2K-char "human" block limitation is a strong talking point that could be used without naming Letta specifically: "Other tools give you 2,000 characters to describe a person. We give you a structured behavioral model."

### vs ChatGPT Memory (opaque, non-portable)
**Communicated on Vision page.** The ownership argument is well-articulated there ("The memory of you is an asset, and right now it belongs to the platform"). The Vision page also calls out the model-upgrade discontinuity problem. This is strong but buried in a long essay.

### vs Claude Memory (on-demand, shallow)
**Not explicitly addressed.** Claude's memory is newer and less understood by the market. The Try-It page's "Where to use your brief" section implicitly positions Base Layer as a complement to Claude, not a replacement.

### What's the unique angle?
Base Layer's unique angle is the **transformation from facts to behavioral predictions with epistemic rigor** — false-positive guards, provenance traces, commitment depth classification. No competitor does this. The examples demonstrate it. The research page documents it.

**Is it communicated?** Partially. The hero carousel shows it. The Vision page argues for it philosophically. But there's no single page that says: "Here's what makes us different from Mem0, Letta, and ChatGPT Memory" in plain terms. A comparison table on the site (even a simplified one) would be high-leverage.

---

## Conversion Funnel

### "Interesting" to "I want this"
Current flow: Hero (see the value) -> Examples (see it demonstrated) -> Try It (do it yourself). This is a solid three-step funnel.

**Gap:** There's no intermediate step between "interesting" and "I'll install Python and run a CLI." The hosted version interest capture on Try-It is the right instinct — many visitors will want to see their OWN identity model before committing to a technical install. A "paste 5 paragraphs of your writing and see a preview" web demo would be the highest-converting addition possible.

### Waitlist
Yes, there is a waitlist. It appears:
1. On the homepage (at the bottom, via Waitlist component with "Follow the Research" CTA)
2. On the Try-It page (both "hosted version" interest capture and "Follow the Research")

The waitlist is positioned as "follow the research" rather than "get early access." This is an honest framing but reduces urgency. Consider dual framing: "Follow the research" for the curious, "Get notified when hosted version launches" for the action-oriented.

### Pricing
No pricing page. The cost table on Try-It shows API costs ($0.10-$1.50), which is effectively the "price" for the self-hosted version. This is fine for the current stage but will need a pricing page when the hosted version ships.

### API Access
No API documentation on the site. The MCP server is mentioned on Try-It but not documented publicly. The GitHub repo presumably has docs, but the website doesn't link to API-specific documentation.

### CTA
Primary CTA: "Try It" (accent button in hero and nav)
Secondary CTA: "See Examples" (border button in hero)
Tertiary CTA: "Follow the Research" / waitlist email capture

The CTA hierarchy is correct. "Try It" is the right primary action.

---

## What's Missing

### Pricing/Plans Page
Not needed yet. The cost table on Try-It is sufficient. Revisit when hosted version ships.

### API Documentation
Missing. The MCP server is a real product feature that developers would want to explore. A /docs or /api page showing the MCP identity resource + recall/search/trace tools would convert developer interest.

### Demo Video
**This is the single highest-impact missing asset.** A 60-90 second video showing: (1) export ChatGPT conversations, (2) paste the prompt into Claude Code, (3) watch the pipeline run, (4) read the resulting identity model, (5) paste it into Claude and see the difference in conversation quality. This would convert more visitors than any page redesign.

### Social Proof / Testimonials
29 thinker pages live, 3 waves of outreach sent, Scott Alexander engaged enough to attempt 3 unlocks. None of this is on the site. Even a simple "Built identity models for 92 subjects from Benjamin Franklin to modern technologists" line would add credibility. If any thinker gives permission to quote their reaction, that becomes the most valuable element on the site.

### Clearer Onboarding Path
The Try-It page is good but assumes technical capability. The funnel needs a non-technical entry point: either the hosted version or a web-based demo/preview.

### A "How It Works" Section
The pipeline (Import -> Extract -> Author -> Compose) is a four-step story that could be visualized on the homepage below the hero. Show the transformation: raw text -> extracted facts -> behavioral layers -> unified brief. This would bridge the gap between "interesting concept" and "I understand what this does."

### Thinkers Directory
29 live pages, invisible to organic visitors. Even a curated public gallery (opt-in only) of 3-5 willing thinkers would be powerful social proof and a content discovery engine.

---

## Outreach Assessment

### Current State
- 29 thinker pages live
- Wave 1: 15 emails sent 2026-03-19. Scott Alexander active (3 unlock attempts, sent raw identity model). Maggie Appleton active.
- Wave 2: 10 emails sent 2026-03-23. 3 bounced (Dan Luu, Derek Thompson, Nathan Lambert).
- Wave 3 partial: 4 sent (Bernie Sanders, Ivan Bercovich, Jonathan Fulton, Eli Tyre).
- 12 follow-up drafts ready.

### Response Rate
From 29 emails delivered (25 Wave 1+2 minus 3 bounces, plus 4 Wave 3): 2 confirmed engaged (Scott Alexander, Maggie Appleton) = ~7% engagement rate. This is within normal range for cold outreach to high-profile individuals. The question is whether "engaged" converts to "willing to be quoted/featured."

### What's Working
- **The product IS the outreach.** Sending someone their own identity model is an inherently compelling cold email. No one else can do this.
- **Password-gating creates intrigue.** Scott Alexander tried 3 times to unlock his page.
- **Prediction picks** (matching against Aarik's identity model for genuine resonance) make each email personal without being creepy.

### What Could Be Improved
- **Follow-up timing.** 12 drafts ready but held. The window between "interesting cold email" and "forgotten" is about 5-7 days. Follow-ups should go out promptly after initial send.
- **Bounce recovery.** 3 bounced emails (Dan Luu, Derek Thompson, Nathan Lambert) need correct addresses found and resent.
- **Conversion path from engagement to permission.** If Scott Alexander or Maggie Appleton say "this is cool" — what's the ask? Permission to feature them publicly? A quote for the site? An intro to their network? Define the conversion goal before following up.

### LinkedIn / Reddit Strategy
- **LinkedIn:** Stacking test comparison post published (S96). Predicate spec post drafted. LinkedIn is good for building credibility with the AI/dev audience.
- **Reddit:** 19 subreddits identified, post finalized, starting with r/LocalLLaMA. Reddit is the highest-leverage channel for developer adoption. The r/LocalLLaMA audience specifically cares about local-first, open-source AI tools — direct overlap with Base Layer's positioning.

**Reddit should be the top distribution priority.** One well-received r/LocalLLaMA post can drive more GitHub stars and Try-It traffic than months of email outreach.

---

## Recommendations: Top 5 This Week

### 1. Record a 90-second demo video
Show the full flow: export -> paste prompt -> pipeline runs -> read your identity model -> use it in Claude. Put it on the homepage above the fold or immediately below the hero. This is the single highest-converting asset you can create. A visitor who watches 90 seconds of the pipeline running will understand the product better than reading any amount of copy.

### 2. Post on r/LocalLLaMA
The post is finalized, the subreddits are identified. Ship it. Lead with the predicate spec (46 verbs to describe any person) or the compression finding (20% of facts is enough for identification). r/LocalLLaMA values technical depth, open source, and local-first architecture — all Base Layer strengths.

### 3. Add a "How It Works" visual to the homepage
Four steps: Import -> Extract -> Author -> Compose. Show what goes in (messy conversations) and what comes out (structured behavioral model). This bridges the comprehension gap between the hero pitch and the Try-It page. Does not need to be complex — even a static diagram with short descriptions per step.

### 4. Send follow-up emails
The 12 drafts are ready. Update fact counts, send them. The engagement window is closing. Every day without follow-up reduces conversion probability. Prioritize Scott Alexander (already engaged), Maggie Appleton (already engaged), and Kevin Kelly (only real V2, best demo of the product improving with more data).

### 5. Create one "normal person" example
The historical examples (Franklin, Buffett) are impressive but feel academic. Add an anonymized example built from ChatGPT conversations or journal entries — the actual use case for 95% of potential users. This could be Aarik's own model (already exists), presented with appropriate context. Show that this works on YOUR conversations, not just famous autobiographies.

---

## Summary

The website is surprisingly strong for a bootstrapped pre-launch project. The hero messaging is clear and differentiated. The examples are the best demonstration of value. The Try-It page is practical and well-structured. The Vision essay is intellectually compelling.

The gaps are: (1) no demo video, (2) no non-technical entry point, (3) competitive differentiation exists in internal docs but not on the site, (4) 29 thinker pages are invisible to organic visitors, and (5) outreach follow-ups are stalled.

The product IS the GTM strategy — sending people their own behavioral models is the most compelling cold outreach possible. The bottleneck is not messaging or positioning. It's distribution. Get the Reddit post out, get the demo video up, and follow up on the engaged thinkers.
