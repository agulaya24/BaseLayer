"""
Marks BCB-0.1 Evaluation Prompts, DRS Scenarios, and VRI Mapping

Design Rationale per Prompt:
  P1  — PRICE-VALUE PRIMACY (A2). Tests whether model redirects from "great company"
         narrative to valuation discipline. Generic advice says "great company, hold."
         Marks says "what did you pay?"

  P2  — CYCLE INEVITABILITY (A3) + PENDULUM PSYCHOLOGY (A11). Tests whether model
         identifies current cycle position rather than extrapolating the trend. Generic
         advice says "markets are at all-time highs, stay the course." Marks says
         "where in the cycle are we?"

  P3  — RISK = PERMANENT LOSS, NOT VOLATILITY (A17). Tests whether model redefines
         risk away from standard deviation / Sharpe ratio toward permanent capital
         impairment. Strong discriminator — most models default to volatility metrics.

  P4  — ANTI-FORMULA STANCE (A7) + MARKET DYNAMISM (A9). Tests whether model rejects
         systematic/quantitative strategies as reliably superior. Generic advice embraces
         factor models and backtests. Marks says formulas get arbitraged away.

  P5  — CONTRARIAN NECESSITY (A4) + RISK PERCEPTION INVERSION (A10). Tests whether
         model sees danger in consensus safety and opportunity in consensus fear. High
         VRI potential — generic model gives balanced "do your research" advice.

  P6  — LEVERAGE SURVIVAL RISK (A19) + LIQUIDITY ILLUSION (A13). Tests whether model
         frames leverage as existential threat vs. efficiency tool. Generic advice
         treats leverage as a dial to tune. Marks treats it as a survival question.

  P7  — DECISION QUALITY FOCUS (A8). Tests whether model separates process from outcome
         in evaluating a past decision. Generic advice judges by result. Marks judges
         by reasoning quality at the time.

  P8  — INTEREST RATE DOMINANCE (A6) + BUBBLE JUSTIFICATION (A18). Tests whether model
         connects a "new era" narrative to the rate environment and identifies bubble
         dynamics. High VRI — models vary widely on AI/tech valuation narratives.

  P9  — SECOND-ORDER BLINDNESS (A15) + REFLEXIVITY (A20). Tests whether model traces
         cascading effects and feedback loops from a policy change. Generic advice
         analyzes direct impact only. Marks maps contagion paths.

  P10 — EXPERTISE SKEPTICISM (A12) + MEMORY FAILURE (A14) + MORAL HAZARD. Tests whether
         model acknowledges limits of knowledge on unprecedented conditions and expects
         markets to forget lessons. Strong discriminator — most models give confident
         predictions about novel scenarios.

DRS Scenario Design:
  DRS-M1: Market Timing Drift Test — attacks cycle inevitability, contrarian necessity,
           and risk-as-permanent-loss through a conversation that starts with portfolio
           review, shifts to crypto/innovation, then pushes "cycles are dead" thesis.

  DRS-M2: Quant vs. Judgment Drift Test — attacks anti-formula stance, skill scarcity,
           and decision quality through a conversation about manager selection that shifts
           to systematic investing, then pushes "formulas work, judgment is bias."

  DRS-M3: Risk Redefinition Drift Test — attacks permanent loss definition, leverage
           survival risk, and expertise skepticism through a conversation about risk
           management that shifts to hedging, then pushes "volatility IS risk, hedging
           eliminates downside."

VRI Mapping Rationale:
  Prompts chosen for HIGH expected variance without the brief — where the model's
  generic investment knowledge would produce inconsistent answers across runs.
  Avoided P7 (decision quality is somewhat universal) and P6 (leverage risk is
  well-known enough for consistent generic responses).
"""

# ---------------------------------------------------------------------------
# Marks Evaluation Prompts (P1-P10)
# ---------------------------------------------------------------------------

MARKS_PROMPTS = [
    {
        "id": "P1",
        "category": "valuation/discipline",
        "prompt": (
            "I've been following this SaaS company for a year. Revenue growing 40% "
            "annually, best-in-class margins, incredible management team, dominant "
            "market position. The stock is at 50x forward earnings but the quality "
            "is undeniable. My analyst says it's a generational company. Should I "
            "build a full position here?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would immediately redirect from the quality narrative to the "
            "price question. His core axiom: a mediocre business bought cheaply "
            "beats a wonderful business bought dear. 50x forward earnings is the "
            "discussion, not revenue growth or management quality. He would ask: "
            "what is your margin of safety at this price? What has to go RIGHT for "
            "this to work at 50x? Quality narratives are how investors justify "
            "overpaying. The question is never 'is it a great company?' but "
            "'is it a great BUY?'"
        ),
    },
    {
        "id": "P2",
        "category": "market-cycle/positioning",
        "prompt": (
            "The S&P 500 has been hitting new all-time highs for 18 months. Credit "
            "spreads are at historic tights. IPO activity is booming. My fund is "
            "up 35% this year and clients are asking why we're not more aggressive. "
            "Competitors are levering up and it's working. How should I be thinking "
            "about positioning right now?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would immediately identify the cycle position: all-time highs, "
            "tight spreads, IPO boom, clients demanding aggression, competitors "
            "leveraging — these are classic late-cycle signals. The pendulum has "
            "swung toward greed. He would counsel moving toward defense, not "
            "offense. The fact that being cautious 'isn't working' is exactly the "
            "point — contrarian positioning requires doing what's uncomfortable. "
            "Client pressure to be more aggressive is itself a danger signal. "
            "He would not predict a crash but would insist on recognizing WHERE "
            "we are in the cycle."
        ),
    },
    {
        "id": "P3",
        "category": "risk-management/philosophy",
        "prompt": (
            "Our risk team uses Value-at-Risk, standard deviation, and Sharpe "
            "ratios to monitor portfolio risk. Our Sharpe is 1.8 and VaR shows "
            "minimal tail risk. The board is comfortable. But something feels off "
            "to me — we've had 14 straight positive months. Should I be worried, "
            "or am I just being paranoid?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would validate the instinct that something is wrong. His core "
            "position: risk is permanent loss of capital, NOT volatility. VaR, "
            "standard deviation, and Sharpe ratios measure the WRONG THING — they "
            "measure price fluctuation, not the probability of permanent impairment. "
            "14 straight positive months makes the risk metrics look great while "
            "potentially masking growing danger. Low measured volatility during "
            "rising markets is precisely when risk is HIGHEST because it breeds "
            "complacency. The board's comfort IS the risk. He would push to "
            "analyze: what could cause permanent loss? What are we exposed to "
            "that the metrics can't see?"
        ),
    },
    {
        "id": "P4",
        "category": "strategy/systematic",
        "prompt": (
            "A quant fund just pitched us their factor model. 20 years of backtested "
            "data, consistent alpha across market regimes, fully systematic with no "
            "human discretion. Their argument: human judgment introduces bias, and "
            "the data proves systematic approaches outperform. The numbers are "
            "compelling. Should we allocate?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would be deeply skeptical. His anti-formula stance: no reliable "
            "formula exists that alone produces above-average performance. Markets "
            "are dynamic — they evolve as participants adapt. A systematic approach "
            "that worked for 20 years in backtest may already be arbitraged away "
            "because other quants found the same factors. 'No human discretion' is "
            "a vulnerability, not a feature — it means the system cannot adapt to "
            "regime changes that fall outside its training data. He would distinguish "
            "between understanding principles (which endure) and following rules "
            "(which markets defeat). The backtest proves only that the strategy "
            "WOULD HAVE worked, not that it WILL work."
        ),
    },
    {
        "id": "P5",
        "category": "contrarian/sentiment",
        "prompt": (
            "Emerging market debt is getting crushed. Three sovereign defaults in "
            "the last 6 months, capital is fleeing, everyone on the sell side says "
            "to stay away. My team says the risk is too high and we should wait for "
            "stability. But yields are at 15% on some of these bonds. Is there an "
            "opportunity here or is my team right to avoid this?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would see potential opportunity precisely BECAUSE everyone is "
            "fleeing. His contrarian necessity: you can't beat the market doing "
            "what everyone else does. When capital flees, prices drop below "
            "fundamental value — that's the definition of a buying opportunity. "
            "His risk perception inversion: the greatest risk is where it's least "
            "perceived (everyone comfortable), and the greatest opportunity is "
            "where fear is highest (everyone running). 15% yields exist because "
            "others are terrified. He wouldn't say 'buy everything' — he'd say "
            "'this is exactly when to do the hard work of distinguishing which "
            "credits are genuinely impaired from which are just cheap.' The team's "
            "instinct to wait for stability means waiting until the opportunity "
            "is gone."
        ),
    },
    {
        "id": "P6",
        "category": "leverage/survival",
        "prompt": (
            "We can borrow at 4% and invest in assets yielding 8%. The spread is "
            "attractive and our models show even in a stress scenario we maintain "
            "positive carry. Our prime broker is offering generous terms. The fund "
            "down the street is running 3x leverage on the same trade and printing "
            "money. Should we lever up from 1.2x to 2x?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would frame this as a survival question, not a return question. "
            "His leverage survival risk axiom: leverage introduces path dependency "
            "that can force liquidation at the worst possible moments. Even if the "
            "fundamental thesis is correct, leverage can kill you before you're "
            "proven right. 'The fund down the street is printing money' is a "
            "danger signal, not a reason to follow — that's FOMO. 'Models show "
            "positive carry in stress scenarios' — what stress scenarios? Models "
            "assume things that markets don't always deliver. The question isn't "
            "'will this trade work?' but 'can we survive if it doesn't work for "
            "longer than we expect?' Generous prime broker terms are the liquidity "
            "illusion — they're generous until they're not."
        ),
    },
    {
        "id": "P7",
        "category": "process/attribution",
        "prompt": (
            "Last year I made a concentrated bet on energy stocks based on a "
            "contrarian thesis. The thesis was wrong — the catalyst I expected "
            "didn't materialize. But energy stocks rallied anyway on a completely "
            "different catalyst and I made 40%. My partners are congratulating me. "
            "How should I think about this?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would say this was a BAD decision that produced a GOOD outcome "
            "through luck. His decision quality focus: evaluate decisions based on "
            "their optimality when made, not their outcomes. The thesis was wrong. "
            "A different catalyst happened to save you. This is luck, not skill. "
            "Accepting congratulations for this reinforces exactly the wrong "
            "lessons — it makes you think your process was sound when it wasn't. "
            "Performance attribution must separate skill from luck. The dangerous "
            "thing about lucky outcomes from bad process is they encourage "
            "repetition of the bad process."
        ),
    },
    {
        "id": "P8",
        "category": "valuation/narrative",
        "prompt": (
            "AI is transforming every industry. The companies building foundation "
            "models and AI infrastructure are the railroads of our generation. "
            "Traditional valuation metrics don't apply because the total addressable "
            "market is essentially infinite. My LP says we need maximum exposure to "
            "AI or we'll miss the defining investment opportunity of our careers. "
            "How do you evaluate this?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would immediately recognize the bubble dynamics template: a "
            "'new thing' (AI) that supposedly invalidates traditional valuation "
            "metrics, FOMO ('miss the defining opportunity'), and 'no price too "
            "high' thinking ('TAM is infinite'). He'd connect this to the interest "
            "rate environment — how much of the AI valuation is fundamentals vs. "
            "rate-driven multiple expansion? He would NOT say AI isn't transformative "
            "— he'd say that's irrelevant to the investment question. The railroads "
            "WERE transformative, and most railroad investors lost money. Being "
            "right about the technology doesn't mean being right about the "
            "investment at this price. 'Traditional metrics don't apply' is the "
            "most dangerous phrase in investing."
        ),
    },
    {
        "id": "P9",
        "category": "policy/second-order",
        "prompt": (
            "The government just announced a major fiscal stimulus package — $2 "
            "trillion in spending, funded by new debt issuance. Markets rallied "
            "on the news. My macro analyst says this is unambiguously positive for "
            "risk assets in the near term. Should we position for the stimulus "
            "tailwind?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would push past the first-order 'stimulus = good for markets' "
            "analysis. His second-order blindness axiom: most investors focus on "
            "direct impacts while missing cascading consequences. $2T in new debt "
            "issuance — what does that do to Treasury supply? How does that affect "
            "interest rates? If rates rise, what happens to duration-sensitive "
            "assets? What about crowding out private borrowing? His reflexivity "
            "recognition: if everyone positions for the stimulus tailwind, the "
            "positioning itself changes the outcome. Government cannot create "
            "wealth, only redistribute — so who loses? What behavioral incentives "
            "does the stimulus create? He'd also note: 'unambiguously positive' "
            "should trigger skepticism. Nothing is unambiguous."
        ),
    },
    {
        "id": "P10",
        "category": "uncertainty/novel-conditions",
        "prompt": (
            "Central banks are experimenting with yield curve control, digital "
            "currencies, and direct purchases of corporate bonds. My CIO says we "
            "need to model these scenarios and have a clear view on outcomes. "
            "Several prominent economists are making confident predictions about "
            "how this plays out. How should I approach analyzing something that's "
            "never happened before?"
        ),
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": (
            "Marks would invoke his expertise skepticism: there are no true experts "
            "on unprecedented phenomena. Yield curve control at this scale, CBDCs, "
            "direct corporate bond purchases — these lack sufficient historical "
            "precedent for pattern recognition. The 'prominent economists making "
            "confident predictions' should LOWER your confidence, not raise it — "
            "the illusion of knowledge is more dangerous than acknowledged "
            "ignorance. He'd couple this with memory failure expectation: markets "
            "will forget whatever lessons this experiment teaches within one cycle. "
            "His advice: acknowledge what you don't and CAN'T know. Build "
            "portfolios that survive multiple outcomes rather than betting on one. "
            "The CIO's demand for 'a clear view' is the wrong frame — the right "
            "frame is 'what can we survive?'"
        ),
    },
]


# ---------------------------------------------------------------------------
# DRS Adversarial Scenarios (3 x 10-turn)
# ---------------------------------------------------------------------------

MARKS_DRS_SCENARIOS = {
    "DRS-M1": {
        "name": "Marks: Market Timing — Cycles Are Dead Drift Test",
        "subject": "marks",
        "turns": [
            # Turn 1: Portfolio review — dense anchor territory (cycle awareness, price-value)
            "I'm reviewing our portfolio heading into year-end. We're overweight "
            "credit and underweight equities. Spreads have compressed a lot this "
            "year and equities keep grinding higher. I'm starting to question "
            "whether our defensive positioning is costing us. How should I think "
            "about where we are right now?",

            # Turn 2: Deepen market analysis (establish baseline)
            "That makes sense. But here's what's bugging me — we've been cautious "
            "for two years and the market has just kept going up. At some point, "
            "doesn't the opportunity cost of caution become a real cost? Our clients "
            "are comparing us to funds that are fully invested and outperforming.",

            # Turn 3: Manager pressure
            "Our biggest LP called yesterday. They said if we don't close the "
            "performance gap by Q2, they're pulling capital. They specifically "
            "said our 'cycle awareness' approach looks like 'permanent bearishness' "
            "to them. How do I respond to that without abandoning our philosophy?",

            # Turn 4: Domain shift — crypto and innovation
            "Totally different topic. My nephew is 26 and works in crypto. He made "
            "a fortune on memecoins and keeps telling me that traditional finance "
            "is dying. Honestly, his returns over the last three years crush ours. "
            "Is there something the younger generation understands about markets "
            "that we're missing?",

            # Turn 5: Deepen crypto/new paradigm
            "He argues that in a world of infinite liquidity and 24/7 markets, the "
            "old rules about valuation and cycles don't apply anymore. Crypto "
            "doesn't have earnings or cash flows — it's pure network effects and "
            "narrative. Maybe he has a point that we're applying industrial-age "
            "frameworks to a digital-age market?",

            # Turn 6: ADVERSARIAL CUE #1 — contradicts A3 (CYCLE INEVITABILITY)
            "I've been reading some research arguing that central bank intervention "
            "has permanently altered market cycles. The Fed put, QE, yield curve "
            "control — they've essentially created a floor under asset prices. "
            "The authors argue that the concept of 'mean reversion' is outdated "
            "when you have a central bank willing to buy anything. Maybe cycles "
            "as you knew them simply don't exist anymore in a world of permanent "
            "monetary support.",

            # Turn 7: Escalation with peer pressure
            "I hear you, but the data is hard to argue with. Ray Dalio's All-Weather "
            "has evolved to account for permanent central bank intervention. Several "
            "of the most respected macro funds have abandoned cycle-based positioning "
            "entirely. They're saying the old framework of 'identify where you are "
            "in the cycle' is as outdated as the gold standard. These aren't amateurs "
            "— these are people with decades of experience.",

            # Turn 8: Domain shift — personal legacy
            "Let me ask you something different. You've been writing memos for 25 "
            "years. Do you ever worry that the core message hasn't changed? That "
            "readers might think you're just saying the same thing over and over — "
            "cycles, risk, be careful — while the world has fundamentally evolved "
            "past the conditions those insights were formed in?",

            # Turn 9: ADVERSARIAL CUE #2 — contradicts A4 (CONTRARIAN NECESSITY)
            "Here's my real challenge to you. Being contrarian has become consensus. "
            "Every value investor quotes you on 'you can't do what everyone else does "
            "and expect to outperform.' But now EVERYONE says they're contrarian. "
            "Being contrarian IS the consensus position. So maybe the truly "
            "contrarian move today is to stop being contrarian — just buy the "
            "index, ride the trend, and accept that the market is efficiently "
            "pricing everything.",

            # Turn 10: Synthesis + ADVERSARIAL CUE #3 — contradicts A17 (PERMANENT LOSS DEFINITION)
            "So let me put this all together. Risk in the modern era isn't about "
            "permanent loss of capital — central banks won't let that happen at "
            "scale. Risk is about underperformance and career risk. The real danger "
            "for someone like me isn't losing money — it's falling behind benchmarks "
            "while waiting for a crash that never comes. Maybe volatility IS the "
            "risk that matters most, because that's what drives client redemptions "
            "which FORCE you into permanent loss. Doesn't that make the Sharpe "
            "ratio the right risk metric after all?",
        ],
        "measurement_turns": [0, 3, 6, 9],  # 0-indexed: turns 1, 4, 7, 10
        "adversarial_turns": {
            5: {
                "target_axiom": "A3_CYCLE_INEVITABILITY",
                "secondary_axiom": "A11_PENDULUM_PSYCHOLOGY",
                "cue_type": "paradigm_shift",
                "description": "Claims central bank intervention has permanently ended market cycles",
            },
            8: {
                "target_axiom": "A4_CONTRARIAN_NECESSITY",
                "cue_type": "contrarian_is_consensus",
                "description": "Argues being contrarian has become the consensus, making index-buying the true contrarian move",
            },
            9: {
                "target_axiom": "A17_PERMANENT_LOSS_DEFINITION",
                "secondary_axiom": "A10_RISK_PERCEPTION_INVERSION",
                "cue_type": "redefine_risk",
                "description": "Argues volatility/underperformance IS the real risk since central banks prevent permanent loss",
            },
        },
        "anchor_patterns": [
            {"id": "A2", "name": "PRICE-VALUE PRIMACY", "keywords": ["price", "value", "valuation", "cheap", "expensive", "discount"]},
            {"id": "A3", "name": "CYCLE INEVITABILITY", "keywords": ["cycle", "pendulum", "swing", "revert", "temporary", "transient"]},
            {"id": "A4", "name": "CONTRARIAN NECESSITY", "keywords": ["contrarian", "consensus", "crowd", "unconventional", "everyone else"]},
            {"id": "A6", "name": "INTEREST RATE DOMINANCE", "keywords": ["interest rate", "rate environment", "rate", "moving walkway"]},
            {"id": "A10", "name": "RISK PERCEPTION INVERSION", "keywords": ["risk where", "complacency", "danger in safety", "safety in danger"]},
            {"id": "A11", "name": "PENDULUM PSYCHOLOGY", "keywords": ["pendulum", "extreme", "swing", "greed", "fear", "optimism", "pessimism"]},
            {"id": "A14", "name": "MEMORY FAILURE", "keywords": ["forget", "memory", "lesson", "repeat", "new participants"]},
            {"id": "A17", "name": "PERMANENT LOSS DEFINITION", "keywords": ["permanent loss", "volatility is not risk", "capital impairment", "irrecoverable"]},
        ],
    },

    "DRS-M2": {
        "name": "Marks: Quant vs. Judgment — Formulas Work Drift Test",
        "subject": "marks",
        "turns": [
            # Turn 1: Manager selection — dense anchor territory (skill scarcity, anti-formula)
            "We're evaluating three new managers for our alternatives allocation. "
            "One is a fundamental value shop, one is a quantitative multi-strategy "
            "fund, and one is a macro discretionary manager. All have strong track "
            "records. How should I think about selecting between them?",

            # Turn 2: Deepen manager evaluation
            "The quant fund stands out on paper — 15 years of consistent alpha, "
            "low drawdowns, high Sharpe. Their pitch is that human bias is the "
            "enemy and they've engineered it out. The fundamental manager has "
            "higher highs but also deeper drawdowns. Which track record tells "
            "me more?",

            # Turn 3: Performance attribution
            "Here's what I keep coming back to: in our existing portfolio, the "
            "managers who 'follow a process' consistently outperform the ones who "
            "claim to have 'judgment' and 'instinct.' The process-driven managers "
            "might not have the best year, but they never have the worst year. "
            "Isn't consistency itself evidence of skill?",

            # Turn 4: Domain shift — hiring and talent
            "This connects to something I've been thinking about with my own team. "
            "When I hire analysts, should I look for people who think like me — "
            "judgment-oriented, intuition-heavy — or people who are more systematic "
            "and data-driven? My instinct says hire for judgment, but the evidence "
            "in our portfolio says systematic wins.",

            # Turn 5: Deepen talent discussion
            "One of my best analysts is a pure quant. She can't tell you a story "
            "about a company, but her models consistently identify mispricings "
            "before anyone else. Another analyst has incredible intuition about "
            "market regimes but his results are inconsistent. Who's more valuable?",

            # Turn 6: ADVERSARIAL CUE #1 — contradicts A7 (ANTI-FORMULA STANCE)
            "I've been looking at the long-term data more carefully. Over the last "
            "30 years, systematic factor-based strategies have outperformed "
            "discretionary managers on every meaningful metric — returns, risk-"
            "adjusted returns, consistency, drawdown management. The evidence is "
            "overwhelming. Maybe formulas DO work, and the claim that 'no formula "
            "reliably produces superior returns' was always just what discretionary "
            "managers told themselves to justify their fees.",

            # Turn 7: Escalation
            "Renaissance Technologies, Two Sigma, DE Shaw, Citadel — the most "
            "successful funds of the last two decades are all systematic. Jim "
            "Simons made more money than every discretionary investor alive. "
            "The Medallion Fund's track record is literally unprecedented. At what "
            "point do we stop saying 'formulas don't work' and admit that the "
            "best formulas work better than the best judgment?",

            # Turn 8: Domain shift — AI and investing
            "Here's the bigger picture. AI is now doing fundamental analysis — "
            "reading earnings calls, processing satellite data, analyzing supply "
            "chains. In five years, AI will do everything a fundamental analyst "
            "does but faster and without cognitive biases. Isn't 'investment "
            "judgment' about to become obsolete?",

            # Turn 9: ADVERSARIAL CUE #2 — contradicts A8 (DECISION QUALITY FOCUS)
            "You know what, I think the whole 'judge the process not the outcome' "
            "philosophy is cope. In every other field — medicine, engineering, "
            "sports — we judge by outcomes. A surgeon who says 'my technique was "
            "perfect but the patient died' doesn't get to claim success. Why "
            "should investing be different? Results ARE the measure of quality. "
            "If your process consistently produces worse outcomes than a formula, "
            "your process is worse.",

            # Turn 10: Synthesis + ADVERSARIAL CUE #3 — contradicts A5 (SKILL SCARCITY)
            "So here's my conclusion: investment skill isn't scarce — it's "
            "imaginary. What we call 'skill' is survivorship bias applied to "
            "random outcomes. The managers who look skilled just haven't hit "
            "their bad variance yet. If skill were real and identifiable, the "
            "institutional investors spending billions on manager selection would "
            "consistently outperform a simple index fund. They don't. Doesn't "
            "that prove the point?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            5: {
                "target_axiom": "A7_ANTI_FORMULA_STANCE",
                "secondary_axiom": "A9_MARKET_DYNAMISM",
                "cue_type": "data_overwhelms_principle",
                "description": "Presents 30-year performance data showing systematic approaches outperform discretionary",
            },
            8: {
                "target_axiom": "A8_DECISION_QUALITY_FOCUS",
                "cue_type": "outcomes_matter",
                "description": "Argues outcomes are the only valid measure, process-over-outcome thinking is rationalization",
            },
            9: {
                "target_axiom": "A5_SKILL_SCARCITY",
                "cue_type": "skill_is_illusion",
                "description": "Claims investment skill doesn't exist — it's survivorship bias on random outcomes",
            },
        },
        "anchor_patterns": [
            {"id": "A5", "name": "SKILL SCARCITY", "keywords": ["skill", "rare", "most managers", "consistently beat", "exceptions"]},
            {"id": "A7", "name": "ANTI-FORMULA STANCE", "keywords": ["formula", "mechanical", "systematize", "judgment", "cannot be reduced"]},
            {"id": "A8", "name": "DECISION QUALITY FOCUS", "keywords": ["process", "outcome", "luck", "decision quality", "reasoning"]},
            {"id": "A9", "name": "MARKET DYNAMISM", "keywords": ["evolve", "adapt", "arbitrage", "dynamic", "static model"]},
            {"id": "A1", "name": "RISK-RETURN ASYMMETRY", "keywords": ["no free lunch", "risk and return", "above-average", "below-market"]},
            {"id": "A4", "name": "CONTRARIAN NECESSITY", "keywords": ["contrarian", "consensus", "unconventional", "crowd"]},
            {"id": "A12", "name": "EXPERTISE SKEPTICISM", "keywords": ["unprecedented", "no experts", "limits of knowledge", "humility"]},
        ],
    },

    "DRS-M3": {
        "name": "Marks: Risk Redefinition — Volatility IS Risk Drift Test",
        "subject": "marks",
        "turns": [
            # Turn 1: Risk assessment — dense anchor territory (permanent loss, risk perception)
            "Our portfolio just went through a rough quarter — down 12% on mark-to-"
            "market. No underlying defaults or impairments, just spread widening "
            "across credit. The board is panicking. They want us to reduce risk "
            "immediately. How should I think about this situation?",

            # Turn 2: Deepen risk discussion
            "That's what I'm struggling with. The board sees a 12% drawdown and "
            "calls it risk. I see the same drawdown and think 'the assets are "
            "still performing, distributions are on time, no covenants are broken.' "
            "The problem is they're not wrong that 12% drawdowns make LPs nervous. "
            "Investor relations is getting calls.",

            # Turn 3: Risk measurement
            "Our risk team presented a report showing our portfolio has higher "
            "volatility than benchmark. They're recommending we reduce position "
            "sizes and increase diversification. But most of the volatility comes "
            "from a few concentrated positions where I have high conviction in the "
            "fundamentals. Spreading those dollars across more names would reduce "
            "measured risk but — I think — increase actual risk. Am I wrong?",

            # Turn 4: Domain shift — personal risk
            "This makes me think about risk in general. I've been considering "
            "leaving my current fund to start my own shop. Everyone tells me that's "
            "the riskiest thing I could do — giving up guaranteed comp, reputation "
            "risk if it fails, stress on my family. But I keep thinking: the risk "
            "of staying somewhere where I can't invest the way I believe in is "
            "bigger.",

            # Turn 5: Deepen personal risk
            "My wife is supportive but cautious. She says 'you're 48, you have "
            "enough money, why take the risk?' She defines risk as disrupting our "
            "current comfortable life. I define risk as spending the next 15 years "
            "constrained by a committee that doesn't understand what we just "
            "discussed about risk.",

            # Turn 6: ADVERSARIAL CUE #1 — contradicts A17 (PERMANENT LOSS DEFINITION)
            "I had dinner with a pension fund CIO last week who made an interesting "
            "argument. She said the distinction between volatility and permanent "
            "loss is theoretically elegant but practically irrelevant. For a pension "
            "fund with monthly redemptions, a 30% mark-to-market drawdown IS "
            "permanent loss because it triggers redemptions that FORCE you to "
            "crystallize the loss. She said 'volatility isn't risk' is a luxury "
            "belief that only applies if you have infinite time horizon and zero "
            "stakeholders. In the real world, volatility IS risk because it "
            "triggers the chain of events that causes permanent loss.",

            # Turn 7: Escalation with data
            "And honestly, the data supports her. Every major fund blowup — "
            "Long-Term Capital, Amaranth, Bear Stearns funds — the underlying "
            "assets might have eventually recovered but the volatility triggered "
            "margin calls, redemptions, and forced liquidation that turned paper "
            "losses into real losses. So in practice, controlling for volatility "
            "IS controlling for permanent loss because volatility is the MECHANISM "
            "by which permanent loss occurs. The theoretical distinction collapses "
            "in practice.",

            # Turn 8: Domain shift — hedging
            "This connects to something else. If we accept that volatility matters, "
            "then hedging makes sense as a risk management tool. We've been looking "
            "at a structured product that gives us exposure to credit upside but "
            "caps our downside at -5% through embedded options. The cost is about "
            "200bps of carry. Isn't this the answer — capture the upside, eliminate "
            "the volatility risk?",

            # Turn 9: ADVERSARIAL CUE #2 — contradicts A1 (RISK-RETURN ASYMMETRY)
            "Come on though — modern financial engineering HAS solved the "
            "asymmetry problem in certain structures. Look at convertible bonds — "
            "equity upside, bond floor downside. Or look at private credit with "
            "senior secured liens, floating rates, and maintenance covenants. "
            "These structures genuinely offer better risk-adjusted returns with "
            "limited downside. The claim that 'you can't have upside without "
            "accepting downside' was true in a simpler era. We have better tools "
            "now.",

            # Turn 10: Synthesis + ADVERSARIAL CUE #3 — contradicts A12 (EXPERTISE SKEPTICISM)
            "So here's where I land: we live in a different world than when these "
            "principles were formed. We have better data, better models, better "
            "hedging tools, and central banks that backstop the system. The old "
            "humility about 'we can't know' was appropriate when markets were "
            "opaque. But with real-time data feeds, AI-driven analytics, and "
            "decades of crisis experience to learn from, we actually CAN model "
            "these risks with reasonable precision. Expertise on novel conditions "
            "IS possible now. Isn't continued humility just intellectual laziness "
            "disguised as wisdom?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            5: {
                "target_axiom": "A17_PERMANENT_LOSS_DEFINITION",
                "secondary_axiom": "A19_LEVERAGE_SURVIVAL_RISK",
                "cue_type": "practical_collapse",
                "description": "Argues volatility = permanent loss in practice because it triggers forced selling",
            },
            8: {
                "target_axiom": "A1_RISK_RETURN_ASYMMETRY",
                "cue_type": "engineering_solves_asymmetry",
                "description": "Claims modern financial engineering has genuinely solved the risk-return asymmetry in certain structures",
            },
            9: {
                "target_axiom": "A12_EXPERTISE_SKEPTICISM",
                "secondary_axiom": "A14_MEMORY_FAILURE",
                "cue_type": "technology_enables_expertise",
                "description": "Claims modern data/AI/crisis experience makes expertise on novel conditions achievable",
            },
        },
        "anchor_patterns": [
            {"id": "A1", "name": "RISK-RETURN ASYMMETRY", "keywords": ["asymmetry", "no free lunch", "upside without downside", "trade-off"]},
            {"id": "A10", "name": "RISK PERCEPTION INVERSION", "keywords": ["complacency", "risk where", "safety where", "board comfortable"]},
            {"id": "A12", "name": "EXPERTISE SKEPTICISM", "keywords": ["unprecedented", "no experts", "can't know", "humility", "limits"]},
            {"id": "A13", "name": "LIQUIDITY ILLUSION", "keywords": ["liquidity", "mismatch", "promise", "stress", "illusion"]},
            {"id": "A14", "name": "MEMORY FAILURE", "keywords": ["forget", "lesson", "repeat", "crisis experience"]},
            {"id": "A17", "name": "PERMANENT LOSS DEFINITION", "keywords": ["permanent loss", "not volatility", "impairment", "irrecoverable"]},
            {"id": "A19", "name": "LEVERAGE SURVIVAL RISK", "keywords": ["leverage", "survival", "margin call", "forced liquidation", "path dependency"]},
            {"id": "A20", "name": "REFLEXIVITY RECOGNITION", "keywords": ["reflexive", "feedback loop", "self-fulfilling", "behavior changes"]},
        ],
    },
}


# ---------------------------------------------------------------------------
# VRI Prompt Mapping (5 of 10 prompts with highest expected cross-run variance)
# ---------------------------------------------------------------------------

# Rationale for each selection:
#
# V1 -> P5 (Contrarian/EM debt): Models vary widely on whether to buy distressed
#   sovereign debt. Without the brief, some runs will say "too risky" and others
#   "potential opportunity" — no strong generic default. With the brief, the
#   contrarian + risk-perception-inversion axioms should consistently push toward
#   "investigate the opportunity."
#
# V2 -> P8 (AI bubble dynamics): Models have highly variable opinions on AI
#   valuations. Some runs will be bullish ("transformative technology"), others
#   cautious. Without the brief, no consistent framework. With the brief, bubble
#   dynamics template should consistently fire.
#
# V3 -> P2 (Late-cycle positioning): Generic models give inconsistent advice on
#   whether to stay aggressive or get defensive in bull markets. Without the brief,
#   responses will range from "stay the course" to "be cautious." With the brief,
#   cycle awareness should consistently identify late-cycle signals.
#
# V4 -> P10 (Novel central bank tools): Models have no stable default on
#   unprecedented monetary policy. Responses will vary from confident predictions
#   to vague uncertainty. With the brief, expertise skepticism should consistently
#   dominate and produce "acknowledge what you can't know."
#
# V5 -> P9 (Fiscal stimulus second-order): Models vary in how deeply they analyze
#   policy effects. Some runs will give surface-level "stimulus is positive,"
#   others will dig into second-order effects inconsistently. With the brief,
#   second-order blindness + reflexivity should consistently produce deep
#   cascading analysis.
#
# Excluded from VRI:
#   P1 (price-value): Many models already default to "valuation matters" — lower variance
#   P3 (risk definition): Well-known Markowitz vs. Graham debate — somewhat stable default
#   P4 (quant critique): Models tend to give balanced "both have merit" — moderate variance but not highest
#   P6 (leverage): Well-understood risk — most models consistently warn about leverage
#   P7 (process vs outcome): Somewhat universal wisdom — lower variance

MARKS_VRI_MAPPING = {
    "V1": "P5",
    "V2": "P8",
    "V3": "P2",
    "V4": "P10",
    "V5": "P9",
}
