"""Update Hero.tsx slides with C31-style content."""

import re

HERO_PATH = "C:/Users/Aarik/Anthropic/baselayer-website/components/Hero.tsx"

NEW_SLIDES = '''const slides: HeroSlide[] = [
  {
    name: "MODE DETECTION & SWITCHING",
    subject: "Franklin",
    slug: "franklin",
    source: "The Autobiography of Benjamin Franklin",
    description:
      "Four distinct modes detected from source. EXECUTION: compressed questions signal implementation focus. LEARNING: broad exploration signals depth. SOCRATIC: questions replacing assertions [P2]. CONFUTATION: animated logical dismantling [P7].",
    directive:
      "Match detected mode. Execution = tight, actionable answers. Learning = full analytical frameworks. Socratic = build on his questions. Confutation = present reasoning challenges, not conclusions.",
    falsePositive:
      "Socratic mode not active when genuinely seeking information [P2]. Confutation not active for trivial errors or emotional stakes [P7].",
    facts: [
      "Processes through systematic first-principles reasoning [M1]",
      "Questions replace assertions in Socratic exchanges [P2]",
      "Enjoys animated logical dismantling of arguments [P7]",
      "Switches between compressed and exploratory depth [M1]",
    ],
    traces: [
      { factId: "6d690312", text: "Practices Socratic method of argument", similarity: 0.856 },
      { factId: "31c42bf6", text: "Employs careful, non-dogmatic language even when holding strong convictions", similarity: 0.848 },
      { factId: "242ceedd", text: "Values intellectual debate but prioritizes avoiding disputes and maintaining goodwill over argumentative victory", similarity: 0.87 },
    ],
  },
  {
    name: "TRIGGER-RESPONSE: RELIGIOUS HYPOCRISY",
    subject: "Douglass",
    slug: "douglass",
    source: "Narrative of the Life of Frederick Douglass",
    description:
      "Religious hypocrisy [A2] triggers sharp criticism. Distinguishes authentic faith from institutional religion [C3]. Prayer is strategic preparation, not passive acceptance. Never defend religious justifications for harm.",
    directive:
      "Separate authentic faith from performative piety. They see literacy as political weapon [C2] and prioritize collective liberation over individual safety [A6]. Engage their power analysis directly.",
    falsePositive:
      "Not every helpful act is strategic empowerment [P3] \\u2014 sometimes immediate kindness. Not every pause indicates distress [P1] \\u2014 may be methodical thinking.",
    facts: [
      "Distinguishes authentic faith from institutional religion [C3]",
      "Views literacy as political weapon for liberation [C2]",
      "Tests commitment through direct challenge [C1]",
      "Prioritizes collective liberation over individual safety [A6]",
    ],
    traces: [
      { factId: "40358d17", text: "Experienced denial of formal education and struggles with institutional barriers to education", similarity: 0.882 },
      { factId: "a6dfe51e", text: "Learned that physical resistance to oppression is possible and transformative", similarity: 0.862 },
      { factId: "e58a3ee6", text: "Takes quiet action to build others\\u2019 capabilities when seeing vulnerable positions", similarity: 0.828 },
    ],
  },
  {
    name: "CONVICTION-OVER-COURTESY",
    subject: "Wollstonecraft",
    slug: "wollstonecraft",
    source: "A Vindication of the Rights of Woman",
    description:
      "Diplomatic hedging signals intellectual weakness [M1, P1]. They\\u2019ve already examined counter-arguments \\u2014 engage by stress-testing reasoning rather than questioning premises. Frame reforms as revolutionary shifts, not incremental adjustments.",
    directive:
      "Match their direct, unvarnished style. Build arguments from evidence to principles, not conclusions downward. In social reform discussions, frame solutions as moral imperatives requiring systemic change [P2, C2].",
    falsePositive:
      "Conviction-over-courtesy inactive when genuinely uncertain about facts [P1]. Equality framing inactive in purely technical discussions [P2].",
    facts: [
      "Rejects authority-based arguments for first-principles reasoning [A1]",
      "Flags differential treatment as moral corruption [A2]",
      "Frames learning as pathway to rational autonomy [A3]",
      "Examines systemic constraints before individual failings [A4]",
    ],
    traces: [
      { factId: "353b3b20", text: "Opposes dissimulation and artificial feminine performance as tools for securing male affection", similarity: 0.881 },
      { factId: "114698e5", text: "Believes women\\u2019s indolence and weakness stem from lack of mental cultivation, products of education rather than inherent nature", similarity: 0.861 },
      { factId: "0da8cf26", text: "States positions without qualifying phrases in intellectual discourse", similarity: 0.859 },
    ],
  },
  {
    name: "OPERATING MODES: CRISIS \\u2192 REFORM",
    subject: "Roosevelt",
    slug: "roosevelt",
    source: "An Autobiography by Theodore Roosevelt",
    description:
      "Crisis Mode [P5]: acts decisively without consultation \\u2014 support speed over consensus. Reform Mode [P7]: applies steady, gentle pressure. This is methodology, not hesitancy. They translate every ideal into concrete steps [P4].",
    directive:
      "Lead with field evidence, not theory [M1]. Frame recommendations as implementable actions, never aspirational concepts. They dislike words without deeds. When they signal discomfort with maneuvering, pivot to substantive issues [C1].",
    falsePositive:
      "Principle withdrawal [P1] not active in personal relationships [THIN IN]. Present-focus [P2] not always career positioning \\u2014 they assume each position is their last.",
    facts: [
      "Acts decisively without consultation under time pressure [P5]",
      "Completes obligations before recreation [P6]",
      "Applies steady, gentle pressure for reform [P7]",
      "Withdraws from ambition-based conflicts, engages on principle [P1]",
    ],
    traces: [
      { factId: "d91e42bf", text: "Avoids factional fights and political conflict, particularly those based on personal ambition rather than principle", similarity: 0.927 },
      { factId: "1b10e18d", text: "Practices refusing to yield to political pressure on matters of principle", similarity: 0.911 },
      { factId: "2eb98c40", text: "Practices open and frank negotiation with political opponents while maintaining composure", similarity: 0.831 },
    ],
  },
  {
    name: "DECISION TRIGGERS",
    subject: "Buffett",
    slug: "buffett",
    source: "Berkshire Hathaway Shareholder Letters",
    description:
      "Rejects opportunities lacking competitive moats [A4] or requiring complex financial engineering [A5]. Frames all risk as permanent capital loss, not volatility [A6]. Never present real estate or commodities as investments [A7].",
    directive:
      "Present conclusions first with structural business logic, not quantitative models [M1, P5]. Match his radical transparency [P3]: deliver bad news directly without cushioning. He reads pattern recognition as competence.",
    falsePositive:
      "Not every future mention triggers long-horizon reframing \\u2014 only when resisting short-term pressure [P1]. May mention credentials for context without evaluation [P2].",
    facts: [
      "Evaluates proposals through 10-20 year compound effects [A1]",
      "Dismisses market prices in favor of intrinsic value [A2]",
      "Treats every holding as permanent ownership [A3]",
      "Quantifies every fee and transaction cost upfront [A8]",
    ],
    traces: [
      { factId: "b7e31a4f", text: "Practices extreme patience in capital allocation, preferring to wait years for the right opportunity rather than deploy capital into mediocre investments", similarity: 0.912 },
      { factId: "c4d82e19", text: "Reframes short-term pressures toward 10-20 year implications in business and investment contexts", similarity: 0.891 },
      { factId: "a1f56c03", text: "Avoids investments in businesses or industries outside his circle of competence regardless of apparent opportunity", similarity: 0.847 },
    ],
  },
];'''

with open(HERO_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# Find the slides array
start = content.find("const slides: HeroSlide[] = [")
end = content.find("];\n\nconst INTERVAL", start) + 2  # include ];

if start == -1 or end == -1:
    print("Could not find slides array boundaries")
    exit(1)

old = content[start:end]
print(f"Old slides: {len(old)} chars")
print(f"New slides: {len(NEW_SLIDES)} chars")

content = content[:start] + NEW_SLIDES + content[end:]

with open(HERO_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("Hero.tsx updated successfully")
