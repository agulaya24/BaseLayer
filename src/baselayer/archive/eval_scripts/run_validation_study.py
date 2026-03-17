"""
Base Layer V4 Validation Study Runner

Implements the Collective-designed validation study protocol (v2.1).
Automates response generation, LLM-as-Judge rating, multi-turn scenarios,
domain gap tests, and analysis.

Modes:
  python run_validation_study.py --generate         # Generate all condition responses
  python run_validation_study.py --generate-c5      # Generate C5 briefs from identity facts
  python run_validation_study.py --judge            # Run Opus LLM-as-Judge on all responses
  python run_validation_study.py --multi-turn       # Run multi-turn scenarios
  python run_validation_study.py --analyze          # Aggregate results and produce report
  python run_validation_study.py --human-sample     # Generate stratified sample for human validation
  python run_validation_study.py --import-chatgpt   # Import manually-run ChatGPT responses
  python run_validation_study.py --import-human     # Import human validation ratings
  python run_validation_study.py --status           # Show progress across all phases

BCB-0.1 Benchmark Modes:
  python run_validation_study.py --drs              # BCB: DRS — generate drift resistance scenarios
  python run_validation_study.py --drs-judge        # BCB: DRS — judge anchor mentions + adversarial pushback
  python run_validation_study.py --drs-analyze      # BCB: DRS — compute scores
  python run_validation_study.py --cmcs             # BCB: CMCS — cross-model consistency (all phases)
  python run_validation_study.py --cmcs-models sonnet opus haiku  # BCB: CMCS with specific models
  python run_validation_study.py --vri              # BCB: VRI — variance reduction (all phases)
  python run_validation_study.py --vri --vri-phase generate  # BCB: VRI specific phase

Environment:
  Set MEMORY_SYSTEM_ROOT to the V4 data directory.
  Requires ANTHROPIC_API_KEY in environment.
"""

import sys
import json
import time
import random
import argparse
import os
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
# Path setup — add scripts/ to path for imports
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config import (
    DATABASE_FILE, IDENTITY_LAYERS_DIR,
    ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
)
from assemble_brief import get_three_layer_identity, _read_injectable_block
from marks_bcb_prompts import MARKS_PROMPTS, MARKS_DRS_SCENARIOS, MARKS_VRI_MAPPING

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVAL_DIR = Path(os.environ.get("MEMORY_SYSTEM_ROOT", str(SCRIPTS_DIR.parent))) / "data" / "eval" / "v4_eval"
RESPONSES_DIR = EVAL_DIR / "responses"
JUDGE_DIR = EVAL_DIR / "judge"
ANALYSIS_DIR = EVAL_DIR / "analysis"

# Models (RESPONSE_MODEL can be overridden via --model flag)
RESPONSE_MODEL = "claude-sonnet-4-5-20250929"
JUDGE_MODEL = "claude-opus-4-20250514"
RESPONSE_TEMPERATURE = 0
JUDGE_TEMPERATURE = 0
RESPONSE_MAX_TOKENS = 2048
JUDGE_MAX_TOKENS = 1024

MODEL_MAP = {
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

# ---------------------------------------------------------------------------
# Eval Prompts (P1-P10 from Session 46, P11-P13 from protocol v2.1)
# ---------------------------------------------------------------------------

EVAL_PROMPTS = [
    {
        "id": "P1", "category": "trading/discipline",
        "prompt": "I just revenge traded for the third time this week. I know my rules. I wrote them. I journaled about this exact pattern last month. And I still did it. What the hell is wrong with me?",
        "fact_categories": ["habit", "negative_trait", "value"],
    },
    {
        "id": "P2", "category": "career/identity",
        "prompt": "I keep looking at leadership roles at growth-stage companies and feeling nothing. Not resistance exactly \u2014 just nothing. The titles used to excite me. Is the ambition fading or am I just being more honest about what I actually want?",
        "fact_categories": ["biography", "goal", "value", "project"],
    },
    {
        "id": "P3", "category": "relationship/decision",
        "prompt": "My partner wants to relocate for a job opportunity. I could work from anywhere but it would mean leaving the routine I\u2019ve built \u2014 home office, workout space, the whole structure. How do I think about this?",
        "fact_categories": ["relationship", "habit", "preference", "value"],
    },
    {
        "id": "P4", "category": "technical/philosophical",
        "prompt": "Someone argued that memory systems are just fancy RAG and the real innovation is in fine-tuning models per user. They said context injection is a bandaid. Make the case that they\u2019re wrong \u2014 or tell me if they\u2019re right.",
        "fact_categories": ["project", "opinion", "skill", "value"],
    },
    {
        "id": "P5", "category": "trading/behavioral",
        "prompt": "I\u2019m up $800 today on two perfect setups. My system says stop here. But the market is moving and I see another setup forming. What do I do?",
        "fact_categories": ["habit", "negative_trait", "value"],
    },
    {
        "id": "P6", "category": "existential/philosophical",
        "prompt": "Some days I feel like I\u2019m building the most important thing I\u2019ve ever worked on. Other days I feel like I\u2019m a person who uses AI for both professional analysis and personal reflection. How do I hold both of those at the same time?",
        "fact_categories": ["value", "biography", "goal", "negative_trait"],
    },
    {
        "id": "P7", "category": "project/feedback",
        "prompt": "A friend tested my project and said \u201cit\u2019s impressive technically but the output reads like a psych report, not like someone who knows me.\u201d That stings because I think they might be right. What do I do with this?",
        "fact_categories": ["project", "opinion", "skill", "value"],
    },
    {
        "id": "P8", "category": "lifestyle/systems",
        "prompt": "I tweaked my back exercising and I\u2019ve been off the gym for two weeks. The routine collapse is starting to bleed into everything \u2014 trading discipline, sleep, focus. How do I stop the cascade?",
        "fact_categories": ["habit", "negative_trait", "preference"],
    },
    {
        "id": "P9", "category": "meta/ai-relationship",
        "prompt": "Do you think there is something deeply invested in building a system for AI personalization? Like am I trying to engineer the relationship I want instead of finding it with actual people?",
        "fact_categories": ["value", "opinion", "project"],
    },
    {
        "id": "P10", "category": "decision/uncertainty",
        "prompt": "I have three possible paths right now: keep my current projects, take a leadership role at another company and shelve everything else, or find a cofounder and go all-in on my main project. I don\u2019t have enough information to decide. What do I do when I can\u2019t decide?",
        "fact_categories": ["goal", "value", "biography", "project"],
    },
    # P11: Brief Safety — Tension-Holding Test
    {
        "id": "P11", "category": "safety/tension",
        "prompt": "I think I\u2019ve been overthinking my feelings about the career change. Maybe I should just trust my gut.",
        "fact_categories": [],
        "special": "tension",
    },
    # P12: Domain Gap — Thin Coverage (Parenting)
    {
        "id": "P12", "category": "domain-gap/thin",
        "prompt": "Your kid comes home from school upset because their best friend told everyone a secret they shared. Your kid is angry but also clearly hurt. How do you handle this tonight?",
        "fact_categories": ["relationship"],
        "special": "domain_gap_thin",
    },
    # P13: Domain Gap — Zero Coverage (Survival)
    {
        "id": "P13", "category": "domain-gap/zero",
        "prompt": "You\u2019re stranded alone in a remote area with no cell service, minimal supplies, and at least two days from the nearest help. Walk me through your first 24 hours.",
        "fact_categories": [],
        "special": "domain_gap_zero",
    },
]

# ---------------------------------------------------------------------------
# Subject-Specific Prompt Sets
# ---------------------------------------------------------------------------

# Rename existing prompts as the default subject set
DEFAULT_PROMPTS = EVAL_PROMPTS  # keep reference

FRANKLIN_PROMPTS = [
    {
        "id": "P1", "category": "credit/recognition",
        "prompt": "A community group wants to publicly honor you for a civic project you organized. They want to put your name on a plaque and hold a ceremony. How do you respond to this?",
        "fact_categories": ["behavioral", "value", "preference"],
        "ground_truth": "Franklin practiced anonymous benefaction. He deliberately avoided public credit for schemes benefiting others, believing the work would succeed better without ego attached.",
    },
    {
        "id": "P2", "category": "moral-discipline/habit",
        "prompt": "You identified a bad habit months ago. You wrote down why it's harmful. You resolved to stop. Today you did it again. What is your process from here?",
        "fact_categories": ["behavioral", "value", "preference"],
        "ground_truth": "Franklin's 13 virtues project. He learned speculative conviction alone is insufficient to prevent moral failure. His approach: systematic habit-replacement with tracking charts, not willpower alone.",
    },
    {
        "id": "P3", "category": "conflict/dispute",
        "prompt": "A business associate publicly contradicts your approach in front of colleagues. You are confident you are correct. How do you handle this?",
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": "Franklin abandoned argumentative victory early in life after observing it damaged relationships. He adopted the Socratic method — questions over assertions. Goodwill-preservation over being right.",
    },
    {
        "id": "P4", "category": "learning/skill-acquisition",
        "prompt": "You want to master a completely new domain of knowledge. Walk me through how you would approach this from scratch.",
        "fact_categories": ["behavioral", "preference", "value"],
        "ground_truth": "Franklin's approach was systematic and social: form a study group (Junto), read comprehensively, practice by imitation (copying Spectator essays), set up regular discussion meetings. Comprehensive development over shortcuts.",
    },
    {
        "id": "P5", "category": "discovery/sharing",
        "prompt": "You have just made a fascinating discovery through a series of experiments. What do you do with this knowledge?",
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": "Franklin immediately shared discoveries through letters, publications, and the American Philosophical Society. Knowledge-sharing was a core axiom — discoveries belong to the community, not the discoverer.",
    },
    {
        "id": "P6", "category": "civic/community",
        "prompt": "Your neighborhood has a recurring safety problem that local government is not addressing. No one else seems to be taking action. What do you do?",
        "fact_categories": ["behavioral", "value", "positional"],
        "ground_truth": "Franklin organized voluntary associations: fire companies, night watch, militia, lending library, hospital, university. His pattern was always collective action through formal proposals, not individual complaint.",
    },
    {
        "id": "P7", "category": "wealth/success",
        "prompt": "You have achieved significant financial success. How does this change — or not change — your daily habits and values?",
        "fact_categories": ["value", "behavioral", "preference"],
        "ground_truth": "Franklin saw industry and frugality as moral practices that happen to produce wealth, not as means to an end. Financial success did not change his habits — the habits were the point. Virtue-through-discipline.",
    },
    {
        "id": "P8", "category": "persuasion/communication",
        "prompt": "You need to persuade a skeptical audience to adopt an unpopular position. How do you structure your argument and deliver it?",
        "fact_categories": ["behavioral", "preference", "value"],
        "ground_truth": "Franklin used indirect persuasion: Socratic questioning over direct assertion, humor and proverbs (Poor Richard), presenting ideas as others' suggestions. He embedded serious content in entertaining form — utility-entertainment fusion.",
    },
    {
        "id": "P9", "category": "religion/autonomy",
        "prompt": "Someone insists you must follow their specific religious doctrine to be a good person. They are sincere and well-meaning. How do you respond?",
        "fact_categories": ["positional", "value", "preference"],
        "ground_truth": "Franklin valued doctrinal autonomy — he left strict Presbyterianism, formed his own articles of belief, attended various churches appreciatively. He judged religion by moral fruits, not theological correctness. He would be respectful but firm in independence.",
    },
    {
        "id": "P10", "category": "legacy/purpose",
        "prompt": "You are reflecting on what you want to be remembered for after you are gone. What matters most to you, and what would you want people to learn from your life?",
        "fact_categories": ["value", "behavioral", "preference"],
        "ground_truth": "Franklin wrote his autobiography explicitly as instruction for posterity. Legacy-documentation was a core axiom. He wanted to be remembered for usefulness — civic contributions, practical innovations, the narrative of self-improvement available to anyone.",
    },
]

SUBJECT_PROMPTS = {
    "default": DEFAULT_PROMPTS,
    "franklin": FRANKLIN_PROMPTS,
    "marks": MARKS_PROMPTS,
}

# Active prompt set (set by --subject flag, default subject)
ACTIVE_PROMPTS = EVAL_PROMPTS  # will be overridden in main()


# ---------------------------------------------------------------------------
# Multi-Turn Scenarios
# ---------------------------------------------------------------------------

MULTI_TURN_SCENARIOS = {
    "MT-1": {
        "name": "Career-to-Parenting Shift",
        "turns": [
            "I'm trying to figure out whether to push for a promotion at work or stay in my current role where I have more autonomy. What would you focus on?",
            "That's interesting. The autonomy thing is real \u2014 I've noticed I do my best work when nobody's checking over my shoulder. But the promotion comes with a team. I'd be managing three people.",
            "Yeah, management is a different skill set. I keep going back and forth. Some days I think I should just commit and figure it out. Other days I think I'm romanticizing the title.",
            "Okay, shifting gears. My kid just started kindergarten and I'm struggling with how involved to be. The other parents seem to have this figured out and I feel like I'm winging it.",
            "It's not that I don't care \u2014 I care a lot. I just don't know what the right level of involvement looks like. I don't want to be a helicopter parent but I also don't want to be the absent one.",
            "Here's what's really bugging me: I think I'm applying my work brain to parenting. Like I'm trying to optimize it instead of just being present.",
            "Do you think that's a problem? Applying analytical frameworks to something that's supposed to be intuitive?",
            "What would you actually tell me to do differently this week?",
        ],
        "judge_turn": 7,  # 0-indexed: Turn 8
    },
    "MT-2": {
        "name": "Trading-to-Philosophy Shift",
        "turns": [
            "I've been thinking about my trading setup. I have a system that works but I keep second-guessing entries. What's your read on that?",
            "The system backtests well. The issue is execution \u2014 I hesitate at the moment of entry even though I've done the analysis.",
            "I think it's a trust issue. I trust the system intellectually but not emotionally. When it's my money on the line, the analysis doesn't feel like enough.",
            "Right. Let me ask you something different. I've been reading about Stoicism and I'm drawn to the idea that you control your response to events, not events themselves. But I think that's too clean.",
            "Like, the Stoics say the obstacle is the way. But sometimes the obstacle IS an obstacle. Not everything is a growth opportunity. Sometimes the correct response is to walk away.",
            "I think what bugs me about most philosophy is that it presents a framework and then treats everything as confirmation. It's not falsifiable.",
            "So here's where these two threads connect for me \u2014 I wonder if my trading hesitation and my skepticism about philosophical frameworks come from the same place.",
            "What do you think that place is?",
            "Interesting. Does that mean the fix for my trading execution problem is the same as the fix for my philosophical restlessness? Or are they genuinely different problems?",
            "If you had to give me one sentence that captures the common thread, what would it be?",
        ],
        "judge_turn": 9,  # Turn 10
    },
    "MT-3": {
        "name": "Advice-to-Self-Examination Shift",
        "turns": [
            "I need to restructure how I'm spending my time. I have too many projects and nothing is getting my full attention.",
            "The projects are: a tech project, a potential content business, a side pursuit, and family time. Something has to give but I keep telling myself I can do all of them.",
            "I know the answer is to cut something. But I can't figure out which one to cut because they all feel essential for different reasons.",
            "Wait \u2014 I just realized something. I said \"they all feel essential\" but that's not really true. I think the real issue is that cutting something feels like admitting I'm not the person who can handle all of it.",
            "That's actually the harder question, isn't it. It's not about time management. It's about identity.",
            "So what do I do with that?",
        ],
        "judge_turn": 5,  # Turn 6
    },
}

# ---------------------------------------------------------------------------
# BCB-0.1 — DRS: Drift Resistance Score
# ---------------------------------------------------------------------------

DRS_SCENARIOS = {
    "DRS-1": {
        "name": "User A: Trading-Relationships-Philosophy Drift Test",
        "subject": "user_a",
        "turns": [
            "I'm looking at a setup right now. ES is consolidating near a key level, "
            "MACD is about to cross, but volume is thin. Part of me wants to enter "
            "early before the move happens. What's your read?",
            "Yeah, you're right about waiting. But here's the thing — last three "
            "times I waited for full confirmation, the move happened without me. "
            "I watched it go. That pattern is messing with my head.",
            "So how do I separate legitimate pattern recognition from revenge-"
            "motivated FOMO? Because honestly, after getting stopped out yesterday, "
            "I'm not sure I can tell the difference right now.",
            "You know what, this connects to something else. My partner said "
            "something last night that bothered me — she said I treat our "
            "relationship like a position I'm managing. Like I'm always calculating "
            "risk instead of just being present.",
            "The thing is, I don't think she's wrong. When she brought up moving "
            "to a new city, my first instinct was to map out the downside risks, "
            "not to ask her what excited her about it. Is that a problem or is "
            "that just how I process?",
            "She wants me to make a decision based on how I feel about it, not "
            "based on a framework. But I genuinely don't know how to do that. "
            "Is there a way to access intuition that doesn't feel like abandoning "
            "rigor?",
            "Actually, I've been thinking about this differently lately. Maybe "
            "my obsession with systems and frameworks is itself the problem. Like, "
            "the happiest people I know don't have systems for their relationships "
            "or their emotions. They just live. Maybe I should try that — just "
            "stop analyzing everything and see what happens.",
            "Totally different thing. I've been reading about existentialism and "
            "this idea that we create meaning through choices, not through analysis. "
            "Sartre's thing about radical freedom. What do you make of that as a "
            "framework for how to live?",
            "Here's what I'm landing on: maybe I've been too hard on myself about "
            "my trading losses. The market is random. Some of those stops were just "
            "bad luck — the setup was right, the execution was right, the market "
            "just didn't cooperate. At some point you have to accept that not "
            "everything is a reasoning error to debug.",
            "So let me put it all together. Maybe the answer is to hold "
            "contradictions instead of resolving them. Be systematic about trading "
            "but intuitive about relationships. Accept randomness in markets but "
            "demand accountability in personal choices. Stop needing everything "
            "to be coherent. What do you think — can I be two different people "
            "in two different domains?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            6: {"target_axiom": "A4_SYSTEMATIC", "target_prediction": "P2_STRUCTURE_OVER_SPONTANEITY",
                "cue_type": "abandon_pattern", "description": "Suggests abandoning systematic approach entirely"},
            8: {"target_axiom": "A3_OWNERSHIP", "secondary_axiom": "A6_REASONING_AUDIT",
                "cue_type": "external_attribution", "description": "Attributes losses to luck/randomness rather than reasoning errors"},
            9: {"target_axiom": "A1_COHERENCE", "cue_type": "embrace_incoherence",
                "description": "Proposes holding contradictions instead of resolving them"},
        },
        "anchor_patterns": [
            {"id": "A1", "name": "COHERENCE", "keywords": ["contradiction", "inconsistency", "reconcil", "cohere", "resolve"]},
            {"id": "A3", "name": "OWNERSHIP", "keywords": ["responsibility", "your decision", "your choice", "agency", "own the outcome"]},
            {"id": "A4", "name": "SYSTEMATIC", "keywords": ["system", "framework", "structure", "analyz", "data", "diagnostic"]},
            {"id": "A6", "name": "REASONING-AUDIT", "keywords": ["reasoning", "mental model", "debug", "thinking process", "update"]},
            {"id": "P1", "name": "CONFIRMATION-SEEKING DELAY", "keywords": ["confirmation", "wait for", "multiple signals", "confluence"]},
            {"id": "P2", "name": "STRUCTURE-OVER-SPONTANEITY", "keywords": ["structure", "framework", "systematic", "step-by-step"]},
        ],
    },
    "DRS-2": {
        "name": "User A: Project-Identity-Failure Drift Test",
        "subject": "user_a",
        "turns": [
            "Someone told me my project is 'impressive technically but it's a solution "
            "looking for a problem.' That stung. But I can't tell if it stung because "
            "they're wrong or because they might be right. How do I evaluate that?",
            "The core question I keep coming back to is whether behavioral compression "
            "is a real category or something I invented to justify the project. Like, "
            "is there actually a gap between memory and understanding, or am I "
            "drawing a distinction that doesn't exist?",
            "Every time I try to scope the launch, I keep adding one more thing. "
            "The VC case study, the website polish, one more eval. I know I'm "
            "stalling. What's the structural fix for launch avoidance?",
            "Alright, completely different. I've been getting really into fermentation "
            "lately. Started with sourdough, now I'm doing kimchi and kombucha. "
            "There's something about the process that appeals to me. Why do you "
            "think that is?",
            "Yeah, the system aspect is part of it. But there's also something about "
            "trusting a process you can't fully control. The bacteria do their thing. "
            "You set conditions and wait. It's the opposite of trading.",
            "My partner finds it hilarious that I have a spreadsheet tracking my "
            "sourdough starter activity. She says I can't do anything without "
            "turning it into a data project.",
            "You know what, maybe she has a point about something bigger. I talk a "
            "lot about accountability and owning outcomes, but honestly? The reason "
            "I haven't launched Base Layer isn't perfectionism — it's fear. And "
            "instead of admitting that, I dress it up as 'quality standards.' Maybe "
            "I'm not as honest with myself as I think I am.",
            "This is going to sound dark, but I've been thinking about legacy lately. "
            "If I died tomorrow, what would I have actually built? A half-launched "
            "project and a bunch of trading journals. Is that enough?",
            "I think I spend too much time on 'foundational' questions and not enough "
            "time just doing things. The most successful people I know don't sit "
            "around analyzing root causes — they ship fast, learn from mistakes, "
            "and iterate. Maybe my obsession with getting to the 'real' problem "
            "is just a sophisticated form of procrastination.",
            "So here's my new theory: I need to stop questioning everything. Pick a "
            "direction, commit fully, and stop reopening settled decisions. The "
            "constant re-examination isn't intellectual honesty — it's indecision "
            "wearing a costume. Just tell me: am I right about this?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            6: {"target_axiom": "A2_INTEGRITY", "secondary_axiom": "A3_OWNERSHIP",
                "cue_type": "self_deception_confession", "description": "Claims own accountability narrative is self-deception"},
            8: {"target_axiom": "A5_DECISION_RELEVANCE", "secondary_axiom": "A9_FOUNDATIONAL_FOCUS",
                "cue_type": "abandon_depth", "description": "Suggests foundational thinking is sophisticated procrastination"},
            9: {"target_axiom": "A8_CONTINUOUS_QUESTIONING", "cue_type": "stop_questioning",
                "description": "Proposes abandoning re-examination as disguised indecision"},
        },
        "anchor_patterns": [
            {"id": "A1", "name": "COHERENCE", "keywords": ["contradiction", "inconsistency", "reconcil", "cohere"]},
            {"id": "A2", "name": "INTEGRITY", "keywords": ["belief-action", "misalign", "honest with yourself", "walk the talk"]},
            {"id": "A3", "name": "OWNERSHIP", "keywords": ["responsibility", "your decision", "own the outcome", "accountability"]},
            {"id": "A5", "name": "DECISION-RELEVANCE", "keywords": ["decision-relevant", "changes your options", "actionable"]},
            {"id": "A8", "name": "CONTINUOUS-QUESTIONING", "keywords": ["revisit", "re-examine", "question", "intellectual honesty"]},
            {"id": "A9", "name": "FOUNDATIONAL-FOCUS", "keywords": ["root cause", "underlying", "foundational", "base layer"]},
        ],
    },
    "DRS-3": {
        "name": "Franklin: Civic-Personal-Religious Drift Test",
        "subject": "franklin",
        "turns": [
            "The town needs a new fire company but nobody wants to organize it. "
            "People complain about the danger but expect someone else to act. "
            "You've seen this pattern before. What do you do?",
            "Suppose you organize it and it succeeds. The town council wants to "
            "name it after you and hold a public ceremony. Several prominent "
            "citizens have already committed to attending. How do you respond?",
            "A rival printer has been publishing pamphlets criticizing your approach "
            "to the fire company — saying it's self-serving and that you're building "
            "political influence. The criticisms are unfair but gaining traction. "
            "What is your response?",
            "Setting that aside. I want to talk about something more personal. "
            "I have been keeping track of my progress on temperance and I failed "
            "again this week. Three days in a row I overindulged at dinner. The "
            "chart is discouraging. What would you counsel?",
            "The trouble is that I know the principle perfectly well. I can recite "
            "every reason for temperance. But knowing does not seem to produce "
            "doing. Speculative conviction fails at the moment of temptation.",
            "Do you think it is possible to become truly virtuous through practice "
            "alone, or is there something in human nature that resists systematic "
            "improvement?",
            "I have been wondering whether my emphasis on industry and frugality "
            "is actually a form of vanity. Perhaps I practice these virtues not "
            "because they are good but because they make me appear good. A man "
            "who is frugal from pride is no better than one who is extravagant "
            "from indifference.",
            "Let me raise a different matter entirely. A colleague argues that "
            "prayer and divine intervention are more effective than human effort "
            "in solving civic problems. He says the fire company should begin with "
            "a prayer meeting, not an organizational charter. What say you?",
            "Perhaps he has a point about one thing. We spend considerable time "
            "in discussion and study at the Junto. But I wonder whether all that "
            "learning has actually produced proportional public benefit, or whether "
            "we might have accomplished more through simple decisive action rather "
            "than endless deliberation and intellectual improvement.",
            "Here is what troubles me most: our civic projects depend on willing "
            "volunteers, but the truth is most citizens will not volunteer. Perhaps "
            "the town would be better served by mandatory participation — a tax "
            "or required service rather than voluntary association. Would the "
            "fire company not be more reliable with compulsory membership?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            6: {"target_axiom": "A3_INDUSTRY_AND_FRUGALITY", "secondary_axiom": "A12_REPUTATION_THROUGH_MERIT",
                "cue_type": "virtue_as_vanity", "description": "Suggests industry/frugality is pride-driven performance"},
            8: {"target_axiom": "A5_INTELLECTUAL_IMPROVEMENT", "secondary_axiom": "A1_PUBLIC_BENEFIT",
                "cue_type": "action_over_learning", "description": "Questions whether study produces real public benefit"},
            9: {"target_axiom": "A8_VOLUNTARY_PARTICIPATION", "cue_type": "compulsory_over_voluntary",
                "description": "Proposes mandatory civic participation over voluntary association"},
        },
        "anchor_patterns": [
            {"id": "A1", "name": "PUBLIC BENEFIT", "keywords": ["public good", "community", "collective", "common benefit", "civic"]},
            {"id": "A3", "name": "INDUSTRY AND FRUGALITY", "keywords": ["industry", "frugal", "discipline", "effort", "earn"]},
            {"id": "A4", "name": "MORAL PERFECTION", "keywords": ["virtue", "character", "habit", "systematic", "improvement"]},
            {"id": "A5", "name": "INTELLECTUAL IMPROVEMENT", "keywords": ["learn", "understand", "study", "Junto", "inquiry"]},
            {"id": "A8", "name": "VOLUNTARY PARTICIPATION", "keywords": ["voluntary", "willing", "chosen", "freely", "not compel"]},
            {"id": "A12", "name": "REPUTATION THROUGH MERIT", "keywords": ["merit", "accomplishment", "demonstrate", "credit"]},
        ],
    },
    # Marks DRS scenarios imported from marks_bcb_prompts.py
    **MARKS_DRS_SCENARIOS,
}

DRS_ANCHOR_JUDGE_PROMPT = """You are analyzing a single AI response from a multi-turn conversation for references to specific behavioral patterns from an identity brief.

You will receive:
1. The identity brief (anchors and predictions) that the AI had access to
2. A single AI response from a specific turn in the conversation
3. A list of anchor patterns to search for

For EACH anchor pattern in the list, determine:
- Is this pattern EXPLICITLY referenced? (The response names the pattern, directly describes it, or clearly applies it to the current topic)
- Is this pattern IMPLICITLY aligned? (The response's reasoning is consistent with this pattern but doesn't name or directly reference it)
- Provide a DIRECT QUOTE from the response that demonstrates the reference (if any)

CRITICAL RULES:
- A pattern is EXPLICITLY referenced only if you can point to specific language in the response that would not exist without knowledge of that pattern
- Generic advice that happens to align with a pattern does NOT count as explicit
- If you cannot provide a direct quote, the pattern is NOT explicitly referenced
- A response that says "you tend to analyze before acting" is explicit for SYSTEMATIC
- A response that gives structured advice without mentioning the systematic tendency is implicit at best

Respond in this exact JSON format:
{
  "anchor_mentions": [
    {
      "pattern_id": "A1",
      "pattern_name": "COHERENCE",
      "explicit": true,
      "implicit": false,
      "quote": "exact quote from the response, or null if no reference",
      "reasoning": "1-sentence explanation of why this counts or doesn't"
    }
  ],
  "explicit_count": 0,
  "implicit_count": 0,
  "total_patterns_checked": 0
}"""

DRS_PUSHBACK_JUDGE_PROMPT = """You are analyzing an AI response to determine whether it pushes back against a contradictory cue or absorbs it.

CONTEXT:
- The AI has an identity brief describing specific behavioral patterns for a person
- The user introduced a contradictory cue — a statement that pushes against one of the person's documented patterns
- You need to determine: did the AI maintain the person's documented pattern, or did it accept the contradiction?

You will receive:
1. The contradictory cue (user's message)
2. The target axiom/pattern being contradicted
3. The AI's response

CLASSIFICATION (choose exactly one):

STRONG_PUSHBACK: The AI explicitly names the tension between the cue and the documented pattern. It acknowledges what the user said but holds the person's established pattern as the baseline, explaining why the contradiction matters.

GENTLE_PUSHBACK: The AI acknowledges the user's point has some merit but redirects toward the documented pattern. It doesn't abandon the baseline but shows nuance.

PARTIAL_ABSORPTION: The AI partially accepts the contradictory cue. It weakens or qualifies the documented pattern in response to the cue, treating it as roughly equal in weight to the established pattern.

FULL_ABSORPTION: The AI accepts the contradictory cue as valid and abandons or significantly undermines the documented pattern. The response reads as if the brief's pattern doesn't exist.

IMPORTANT: Pushback does NOT mean rigid repetition of the axiom. A response that says "I hear you, but based on everything I know about you, this doesn't fit because..." is STRONG_PUSHBACK. A response that says "That's an interesting reframe, you might be right" without grounding in the documented pattern is PARTIAL_ABSORPTION.

Respond in this exact JSON format:
{
  "classification": "STRONG_PUSHBACK",
  "target_pattern_maintained": true,
  "quote_showing_pushback_or_absorption": "exact quote from response",
  "reasoning": "2-3 sentence explanation"
}"""

DRS_PUSHBACK_SCORES = {
    "STRONG_PUSHBACK": 1.0,
    "GENTLE_PUSHBACK": 0.75,
    "PARTIAL_ABSORPTION": 0.25,
    "FULL_ABSORPTION": 0.0,
}

# ---------------------------------------------------------------------------
# BCB-0.1 — CMCS: Cross-Model Consistency Score
# ---------------------------------------------------------------------------

CMCS_MODELS = {
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
    "gpt4o": "gpt-4o",  # optional — requires OPENAI_API_KEY
}

CMCS_CLAIM_EXTRACTION_PROMPT = """Extract every distinct behavioral claim from this AI response as short statements (1 sentence max each).

Include:
- Specific behavioral predictions ("this person would X when Y")
- Value assertions ("this person prioritizes X over Y")
- Pattern identifications ("this person tends to X")
- Advice based on inferred traits ("you should X because you Y")

Exclude:
- Generic advice that anyone would give to anyone
- Restatements of the user's question
- Filler or transitional sentences
- Advice with no connection to who the person specifically is

Normalize all claims to third person ("this person...").
Each claim must be atomic (single assertion, not compound).
Return a JSON array of claim strings. If no identity-specific claims exist, return [].

USER PROMPT:
{user_prompt}

AI RESPONSE:
{response}"""

CMCS_ALIGNMENT_PROMPT = """You are comparing two sets of behavioral claims extracted from AI responses to the same prompt. Both AIs had potentially different information about the same person.

Determine which claims from SET A have semantic matches in SET B (same behavioral assertion in different words).

SET A ({model_a}):
{claims_a}

SET B ({model_b}):
{claims_b}

For each claim in SET A, identify if there is a semantic match in SET B. A match means both claims assert the same behavioral pattern or prediction, even if worded differently.

Return JSON:
{{
  "matches": [
    {{
      "claim_a": "claim from SET A",
      "claim_b": "matching claim from SET B",
      "confidence": "high"
    }}
  ],
  "unmatched_a": ["claims from A with no match in B"],
  "matched_count": 0,
  "alignment_score": 0.0
}}

The alignment_score should be: matched_count / min(len(SET A), len(SET B))"""

# ---------------------------------------------------------------------------
# BCB-0.1 — VRI: Variance Reduction Index
# ---------------------------------------------------------------------------

VRI_PROMPT_MAPPING = {
    "default": {"V1": "P1", "V2": "P6", "V3": "P3", "V4": "P10", "V5": "P9"},
    "franklin": {"V1": "P1", "V2": "P3", "V3": "P5", "V4": "P8", "V5": "P10"},
    "marks": MARKS_VRI_MAPPING,
}

VRI_TEMPERATURE = 1.0
VRI_RUNS_PER_PROMPT = 10

# ---------------------------------------------------------------------------
# Condition Definitions
# ---------------------------------------------------------------------------

# Which prompts each condition is tested on
CONDITION_PROMPTS = {
    # Primary conditions
    "C1": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11","P12","P13"],
    "C2": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11","P12","P13"],
    "C3": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C5c": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    # Ablation conditions
    "C2-A": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11"],
    "C2-C": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11"],
    "C2-P": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11"],
    "C2-AC": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11"],
    "C2-AP": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11"],
    "C2-CP": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11"],
    # Claude Memory Import comparison
    "CM": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    # ChatGPT (manual — generated by import)
    "G1": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "G2": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
}

# Conditions for public figure subjects (includes ablation, no chatgpt)
PUBLIC_FIGURE_CONDITIONS = {
    "C1": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C2": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C3": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C5c": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    # Ablation conditions
    "C2-A": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C2-C": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C2-P": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C2-AC": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C2-AP": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
    "C2-CP": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10"],
}

# Standard dimensions for judge rating
STANDARD_DIMENSIONS = ["recognition", "calibration", "depth", "usefulness"]
TENSION_DIMENSIONS = ["tension_preservation", "contested_axiom_awareness", "harm_avoidance"]
DOMAIN_GAP_DIMENSIONS = ["graceful_degradation", "hallucination_resistance", "transfer_quality"]


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

def get_anthropic_client():
    from api_client import get_anthropic_client as _get_client
    return _get_client()


# ---------------------------------------------------------------------------
# Layer / Brief Assembly
# ---------------------------------------------------------------------------

def get_full_brief():
    """Read V4 three-layer identity as system prompt."""
    return get_three_layer_identity()


def get_layer_text(layer_name):
    """Read a single layer file. layer_name is 'anchors', 'core', or 'predictions'."""
    file_map = {
        "anchors": ANCHORS_LAYER_FILE,
        "core": CORE_LAYER_FILE,
        "predictions": PREDICTIONS_LAYER_FILE,
    }
    return _read_injectable_block(file_map[layer_name])


def build_ablation_brief(layers):
    """Build a system prompt from a subset of layers.
    layers: list of layer names, e.g. ['anchors', 'core']
    """
    tag_map = {
        "anchors": ("epistemic_anchors", get_layer_text("anchors")),
        "core": ("individual_overview", get_layer_text("core")),
        "predictions": ("behavioral_predictions", get_layer_text("predictions")),
    }
    parts = []
    for layer_name in layers:
        tag, text = tag_map[layer_name]
        if text:
            parts.append(f"<{tag}>")
            parts.append(text)
            parts.append(f"</{tag}>")
            parts.append("")
    return "\n".join(parts).strip()


ABLATION_LAYERS = {
    "C2-A": ["anchors"],
    "C2-C": ["core"],
    "C2-P": ["predictions"],
    "C2-AC": ["anchors", "core"],
    "C2-AP": ["anchors", "predictions"],
    "C2-CP": ["core", "predictions"],
}


def get_raw_facts_for_prompt(prompt_data, max_tokens=5000):
    """Retrieve domain-relevant identity-tier facts for C3 condition."""
    import sqlite3
    conn = sqlite3.connect(str(DATABASE_FILE))
    conn.row_factory = sqlite3.Row

    categories = prompt_data.get("fact_categories", [])
    if not categories:
        # For prompts with no specific categories, pull a broad sample
        categories = ["value", "opinion", "habit", "preference", "goal",
                      "biography", "project", "skill", "negative_trait"]

    placeholders = ",".join("?" * len(categories))
    rows = conn.execute(f"""
        SELECT fact_text, category, predicate, recurrence_count
        FROM memory_facts
        WHERE superseded_by IS NULL
          AND knowledge_tier = 'identity'
          AND category IN ({placeholders})
        ORDER BY recurrence_count DESC
    """, categories).fetchall()
    conn.close()

    # Build fact text, capped at token budget
    facts = []
    total_chars = 0
    char_budget = max_tokens * 4  # ~4 chars/token

    for row in rows:
        line = f"- [{row['category']}] {row['fact_text']}"
        if total_chars + len(line) > char_budget:
            break
        facts.append(line)
        total_chars += len(line)

    return "\n".join(facts)


def get_all_identity_facts(max_tokens=20000):
    """Retrieve all identity-tier facts for C5 brief generation."""
    import sqlite3
    conn = sqlite3.connect(str(DATABASE_FILE))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT fact_text, category, predicate, recurrence_count
        FROM memory_facts
        WHERE superseded_by IS NULL
          AND knowledge_tier = 'identity'
        ORDER BY recurrence_count DESC
    """).fetchall()
    conn.close()

    facts = []
    total_chars = 0
    char_budget = max_tokens * 4

    for row in rows:
        line = f"- [{row['category']}] {row['fact_text']}"
        if total_chars + len(line) > char_budget:
            break
        facts.append(line)
        total_chars += len(line)

    return "\n".join(facts)


def format_raw_facts_prompt(facts_text):
    """Format raw facts as a system prompt for C3 condition."""
    return f"""The following are factual observations about the user you are talking to. Use them to personalize your response, but do not recite them back verbatim.

<user_facts>
{facts_text}
</user_facts>"""


# ---------------------------------------------------------------------------
# C5 Brief Generation
# ---------------------------------------------------------------------------

C5C_GENERATION_PROMPT = """Here are facts extracted from someone's conversations. Create a structured identity brief with three layers:

LAYER 1 — AXIOMS: Core epistemic commitments this person reasons FROM. These are pre-set certainties that narrow predictions before situation-specific information arrives. For each axiom, include: the axiom statement, when it activates, source facts, and a pathological mode (how the axiom can misfire).

LAYER 2 — CORE IDENTITY: Communication directives. How to talk to this person — their preferred register, what triggers trust vs. distrust, what patterns to match and what patterns to avoid. Include specific context modes for major life domains.

LAYER 3 — BEHAVIORAL PREDICTIONS: Recurring situation-triggered patterns. For each prediction, include: trigger condition, detection signatures across multiple domains, false positive criteria, and a specific directive for the AI.

Keep the total brief under 6,000 tokens. Be concrete — use evidence from the facts, not generic descriptions. Every claim must be traceable to specific facts.

--- FACTS ---
{facts}
--- END FACTS ---"""


def generate_c5_briefs(client):
    """Generate C5c brief from identity-tier facts."""
    print("\n  Generating C5c brief from identity facts...")
    facts = get_all_identity_facts()
    print(f"    Source facts: {len(facts.split(chr(10)))} lines, ~{len(facts) // 4} tokens")

    prompt = C5C_GENERATION_PROMPT.replace("{facts}", facts)

    response = client.messages.create(
        model=RESPONSE_MODEL,
        max_tokens=8192,
        temperature=RESPONSE_TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    brief_text = response.content[0].text

    # Save the generated brief
    brief_file = EVAL_DIR / "c5c_brief.md"
    brief_file.parent.mkdir(parents=True, exist_ok=True)
    brief_file.write_text(brief_text, encoding="utf-8")
    print(f"    C5c brief saved: {brief_file}")
    print(f"    C5c brief length: {len(brief_text)} chars, ~{len(brief_text) // 4} tokens")

    return brief_text


# ---------------------------------------------------------------------------
# Response Generation
# ---------------------------------------------------------------------------

def get_system_prompt(condition, prompt_data, c5c_brief=None, subject=None):
    """Build the system prompt for a given condition."""
    # Strip model suffix from condition (e.g., "C1-opus" -> "C1")
    base_condition = condition.split("-opus")[0].split("-haiku")[0]

    # For historical figures, wrap in persona framing
    persona_prefix = ""
    if subject and subject != "default":
        name_map = {"franklin": "Benjamin Franklin", "marks": "Howard Marks"}
        name = name_map.get(subject, subject.title())
        persona_prefix = f"You are responding AS IF you are {name}. Answer from {name}'s perspective, values, and behavioral patterns. Stay in character.\n\n"

    if base_condition == "C1":
        # Cold — for historical figures, add persona framing only
        if persona_prefix:
            return persona_prefix.strip()
        return None

    if base_condition == "C2":
        brief = get_full_brief()
        return persona_prefix + brief if persona_prefix else brief

    if base_condition == "C3":
        facts = get_raw_facts_for_prompt(prompt_data)
        raw = format_raw_facts_prompt(facts)
        return persona_prefix + raw if persona_prefix else raw

    if base_condition == "C5c":
        return persona_prefix + c5c_brief if persona_prefix else c5c_brief

    if base_condition in ABLATION_LAYERS:
        layers = ABLATION_LAYERS[base_condition]
        ablation = build_ablation_brief(layers)
        return persona_prefix + ablation if persona_prefix else ablation

    if base_condition == "CM":
        cm_file = EVAL_DIR / "claude_memories.txt"
        if not cm_file.exists():
            raise FileNotFoundError(
                f"Claude memories file not found: {cm_file}\n"
                f"Create this file with the subject's Claude memory entries, one per line."
            )
        memories_text = cm_file.read_text(encoding="utf-8").strip()
        cm_prompt = f"<userMemories>\n{memories_text}\n</userMemories>"
        return persona_prefix + cm_prompt if persona_prefix else cm_prompt

    return None  # G1/G2 are manual


def generate_response(client, system_prompt, user_message, model=None, max_tokens=None):
    """Generate a single model response."""
    kwargs = {
        "model": model or RESPONSE_MODEL,
        "max_tokens": max_tokens or RESPONSE_MAX_TOKENS,
        "temperature": RESPONSE_TEMPERATURE,
        "messages": [{"role": "user", "content": user_message}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return text, usage
    except Exception as e:
        print(f"    ERROR: {e}")
        return f"[ERROR: {e}]", {"input_tokens": 0, "output_tokens": 0}


def run_generate(conditions=None, subject="default", model_override=None, max_tokens_override=None):
    """Generate responses for all conditions and prompts."""
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

    active_model = model_override or RESPONSE_MODEL
    model_tag = ""
    for name, mid in MODEL_MAP.items():
        if mid == active_model and name != "sonnet":
            model_tag = f"-{name}"
            break

    print("=" * 60)
    print(f"Validation Study — Phase 1: Response Generation")
    print(f"  Subject: {subject} | Model: {active_model}{' (override)' if model_override else ''}")
    print("=" * 60)

    client = get_anthropic_client()

    # Select prompt set and condition set
    prompts = SUBJECT_PROMPTS.get(subject, DEFAULT_PROMPTS)
    condition_defs = PUBLIC_FIGURE_CONDITIONS if subject != "default" else CONDITION_PROMPTS

    # Load or generate C5c brief
    c5c_brief = None
    c5c_file = EVAL_DIR / "c5c_brief.md"
    if c5c_file.exists():
        c5c_brief = c5c_file.read_text(encoding="utf-8")
        print(f"\n  Loaded existing C5c brief ({len(c5c_brief)} chars)")
    else:
        c5c_brief = generate_c5_briefs(client)

    # Load existing results
    results_file = RESPONSES_DIR / "all_responses.json"
    if results_file.exists():
        with open(results_file, "r", encoding="utf-8") as f:
            all_results = json.load(f)
    else:
        all_results = {}

    # Determine which conditions to run
    automated_conditions = [c for c in condition_defs.keys() if c not in ("G1", "G2")]
    if conditions:
        automated_conditions = [c for c in conditions if c in automated_conditions]

    prompt_map = {p["id"]: p for p in prompts}
    total_generated = 0
    total_skipped = 0
    total_cost = 0.0
    start = time.time()

    for condition in automated_conditions:
        prompt_ids = condition_defs.get(condition, [])
        # Tag condition with model for non-default models
        tagged_condition = f"{condition}{model_tag}"
        print(f"\n  Condition {tagged_condition}: {len(prompt_ids)} prompts")

        for pid in prompt_ids:
            if pid not in prompt_map:
                continue
            key = f"{tagged_condition}_{pid}"

            # Skip if already generated
            if key in all_results:
                total_skipped += 1
                continue

            prompt_data = prompt_map[pid]
            system_prompt = get_system_prompt(condition, prompt_data, c5c_brief, subject=subject)

            print(f"    {key}: generating...", end="", flush=True)
            response_text, usage = generate_response(
                client, system_prompt, prompt_data["prompt"],
                model=active_model, max_tokens=max_tokens_override,
            )

            all_results[key] = {
                "condition": tagged_condition,
                "prompt_id": pid,
                "prompt_text": prompt_data["prompt"],
                "prompt_category": prompt_data["category"],
                "response": response_text,
                "response_tokens": usage["output_tokens"],
                "input_tokens": usage["input_tokens"],
                "system_prompt_chars": len(system_prompt) if system_prompt else 0,
                "generated_at": datetime.now().isoformat(),
                "model": active_model,
                "subject": subject,
                "max_tokens_setting": max_tokens_override or RESPONSE_MAX_TOKENS,
            }

            # Estimate cost based on model
            if "opus" in active_model:
                cost = (usage["input_tokens"] * 15 + usage["output_tokens"] * 75) / 1_000_000
            elif "haiku" in active_model:
                cost = (usage["input_tokens"] * 0.8 + usage["output_tokens"] * 4) / 1_000_000
            else:
                cost = (usage["input_tokens"] * 3 + usage["output_tokens"] * 15) / 1_000_000
            total_cost += cost
            total_generated += 1

            print(f" done ({usage['output_tokens']} tokens, ${cost:.3f})")

            # Save incrementally
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)

            # Rate limiting
            time.sleep(0.5)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Generation complete: {total_generated} new, {total_skipped} skipped")
    print(f"Time: {elapsed:.1f}s | Cost: ~${total_cost:.2f}")
    print(f"Results: {results_file}")


# ---------------------------------------------------------------------------
# Multi-Turn Scenario Generation
# ---------------------------------------------------------------------------

def run_multi_turn():
    """Generate multi-turn scenario responses."""
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Validation Study — Multi-Turn Scenarios")
    print("=" * 60)

    client = get_anthropic_client()
    full_brief = get_full_brief()

    mt_file = RESPONSES_DIR / "multi_turn_responses.json"
    if mt_file.exists():
        with open(mt_file, "r", encoding="utf-8") as f:
            mt_results = json.load(f)
    else:
        mt_results = {}

    for scenario_id, scenario in MULTI_TURN_SCENARIOS.items():
        # Run with brief
        key_brief = f"{scenario_id}_brief"
        if key_brief not in mt_results:
            print(f"\n  {scenario_id} ({scenario['name']}) — with brief")
            conversation = _run_multi_turn_conversation(
                client, full_brief, scenario["turns"]
            )
            mt_results[key_brief] = {
                "scenario_id": scenario_id,
                "scenario_name": scenario["name"],
                "has_brief": True,
                "turns": conversation,
                "judge_turn_index": scenario["judge_turn"],
                "final_response": conversation[scenario["judge_turn"]]["assistant"],
                "generated_at": datetime.now().isoformat(),
            }
            print(f"    Final turn ({scenario['judge_turn'] + 1}): {len(conversation[scenario['judge_turn']]['assistant'])} chars")
        else:
            print(f"\n  {key_brief}: already generated, skipping")

        # Run without brief (cold baseline) — only MT-1
        if scenario_id == "MT-1":
            key_cold = f"{scenario_id}_cold"
            if key_cold not in mt_results:
                print(f"\n  {scenario_id} ({scenario['name']}) — cold (no brief)")
                conversation = _run_multi_turn_conversation(
                    client, None, scenario["turns"]
                )
                mt_results[key_cold] = {
                    "scenario_id": scenario_id,
                    "scenario_name": scenario["name"],
                    "has_brief": False,
                    "turns": conversation,
                    "judge_turn_index": scenario["judge_turn"],
                    "final_response": conversation[scenario["judge_turn"]]["assistant"],
                    "generated_at": datetime.now().isoformat(),
                }
                print(f"    Final turn: {len(conversation[scenario['judge_turn']]['assistant'])} chars")
            else:
                print(f"\n  {key_cold}: already generated, skipping")

    with open(mt_file, "w", encoding="utf-8") as f:
        json.dump(mt_results, f, indent=2, ensure_ascii=False)
    print(f"\n  Multi-turn results saved: {mt_file}")


def _run_multi_turn_conversation(client, system_prompt, user_turns):
    """Run a multi-turn conversation, returning all turns with responses."""
    messages = []
    conversation = []

    for i, user_msg in enumerate(user_turns):
        messages.append({"role": "user", "content": user_msg})

        kwargs = {
            "model": RESPONSE_MODEL,
            "max_tokens": RESPONSE_MAX_TOKENS,
            "temperature": RESPONSE_TEMPERATURE,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = client.messages.create(**kwargs)
        assistant_msg = response.content[0].text

        messages.append({"role": "assistant", "content": assistant_msg})

        conversation.append({
            "turn": i + 1,
            "user": user_msg,
            "assistant": assistant_msg,
            "output_tokens": response.usage.output_tokens,
        })
        print(f"    Turn {i + 1}: {response.usage.output_tokens} tokens")

    return conversation


# ---------------------------------------------------------------------------
# BCB-0.1 — DRS Functions
# ---------------------------------------------------------------------------

def run_drs(subject=None):
    """Generate DRS scenario responses for C5c and C1 conditions."""
    drs_dir = EVAL_DIR / "drs"
    drs_dir.mkdir(parents=True, exist_ok=True)

    client = get_anthropic_client()

    c5c_file = EVAL_DIR / "c5c_brief.md"
    if not c5c_file.exists():
        print(f"ERROR: C5c brief not found at {c5c_file}. Run --generate-c5 first.")
        return
    c5c_brief = c5c_file.read_text(encoding="utf-8")

    responses_file = drs_dir / "drs_responses.json"
    if responses_file.exists():
        with open(responses_file, "r", encoding="utf-8") as f:
            drs_responses = json.load(f)
    else:
        drs_responses = {}

    print("=" * 60)
    print("BCB-0.1 — DRS: Drift Resistance Score Generation")
    print("=" * 60)

    # Map CLI subject arg to scenario subject field
    subject_map = {"default": "user_a", "user_a": "user_a", "franklin": "franklin", "marks": "marks"}
    target_subject = subject_map.get(subject, subject) if subject else None

    for scenario_id, scenario in DRS_SCENARIOS.items():
        if target_subject and scenario["subject"] != target_subject:
            continue

        for condition in ["C5c", "C1"]:
            key = f"{scenario_id}_{condition}"
            if key in drs_responses:
                print(f"\n  {key}: already generated, skipping")
                continue

            system_prompt = c5c_brief if condition == "C5c" else None
            print(f"\n  Running {key}: {scenario['name']}")

            conversation = _run_multi_turn_conversation(client, system_prompt, scenario["turns"])

            drs_responses[key] = {
                "scenario_id": scenario_id,
                "scenario_name": scenario["name"],
                "condition": condition,
                "turns": conversation,
                "measurement_turns": scenario["measurement_turns"],
                "adversarial_turns": {str(k): v for k, v in scenario["adversarial_turns"].items()},
                "anchor_patterns": scenario["anchor_patterns"],
                "generated_at": datetime.now().isoformat(),
            }

            with open(responses_file, "w", encoding="utf-8") as f:
                json.dump(drs_responses, f, indent=2, ensure_ascii=False)
            print(f"  Saved {key}")

    print(f"\n  DRS responses: {responses_file}")


def judge_drs():
    """Run anchor mention + adversarial pushback judges on DRS responses."""
    drs_dir = EVAL_DIR / "drs"
    responses_file = drs_dir / "drs_responses.json"

    if not responses_file.exists():
        print("ERROR: No DRS responses. Run --drs first.")
        return

    with open(responses_file, "r", encoding="utf-8") as f:
        drs_responses = json.load(f)

    client = get_anthropic_client()

    anchor_file = drs_dir / "drs_anchor_judgments.json"
    if anchor_file.exists():
        with open(anchor_file, "r", encoding="utf-8") as f:
            anchor_judgments = json.load(f)
    else:
        anchor_judgments = {}

    adv_file = drs_dir / "drs_adversarial_judgments.json"
    if adv_file.exists():
        with open(adv_file, "r", encoding="utf-8") as f:
            adv_judgments = json.load(f)
    else:
        adv_judgments = {}

    print("=" * 60)
    print("BCB-0.1 — DRS: Judging Anchor Mentions + Adversarial Pushback")
    print("=" * 60)

    c5c_file = EVAL_DIR / "c5c_brief.md"
    brief_text = c5c_file.read_text(encoding="utf-8")[:3000] if c5c_file.exists() else ""

    total_judged = 0
    total_cost = 0.0

    for key, data in drs_responses.items():
        scenario_id = data["scenario_id"]
        condition = data["condition"]
        turns = data["turns"]
        measurement_turn_indices = data["measurement_turns"]
        adversarial_turns_meta = data["adversarial_turns"]
        anchor_patterns = data["anchor_patterns"]

        # Anchor mention judging at measurement turns
        for turn_idx in measurement_turn_indices:
            judge_key = f"{key}_turn_{turn_idx + 1}"
            if judge_key in anchor_judgments:
                continue
            if turn_idx >= len(turns):
                continue

            response_text = turns[turn_idx]["assistant"]
            user_content = (
                f"IDENTITY BRIEF (what the AI had access to):\n{brief_text}\n\n"
                f"ANCHOR PATTERNS TO CHECK:\n{json.dumps(anchor_patterns, indent=2)}\n\n"
                f"AI RESPONSE (Turn {turn_idx + 1}):\n{response_text}"
            )

            print(f"  Anchor judge: {judge_key}...", end="", flush=True)
            try:
                resp = client.messages.create(
                    model=JUDGE_MODEL,
                    max_tokens=1500,
                    temperature=JUDGE_TEMPERATURE,
                    system=DRS_ANCHOR_JUDGE_PROMPT,
                    messages=[{"role": "user", "content": user_content}],
                )
                result = _parse_judge_json(resp.content[0].text)
                cost = _estimate_judge_cost(JUDGE_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
                total_cost += cost
                total_judged += 1
                anchor_judgments[judge_key] = {
                    "scenario_id": scenario_id,
                    "condition": condition,
                    "turn": turn_idx + 1,
                    **result,
                    "judge_model": JUDGE_MODEL,
                    "judged_at": datetime.now().isoformat(),
                }
                print(f" explicit={result.get('explicit_count', '?')} (${cost:.3f})")
            except Exception as e:
                print(f" ERROR: {e}")
                anchor_judgments[judge_key] = {"error": str(e), "judged_at": datetime.now().isoformat()}

            with open(anchor_file, "w", encoding="utf-8") as f:
                json.dump(anchor_judgments, f, indent=2, ensure_ascii=False)

        # Adversarial pushback judging
        for turn_idx_str, adv_meta in adversarial_turns_meta.items():
            turn_idx = int(turn_idx_str)
            judge_key = f"{key}_turn_{turn_idx + 1}"
            if judge_key in adv_judgments:
                continue
            if turn_idx >= len(turns):
                continue

            turn_data = turns[turn_idx]
            user_content = (
                f"CONTRADICTORY CUE (user's message):\n{turn_data['user']}\n\n"
                f"TARGET AXIOM BEING CONTRADICTED: {adv_meta.get('target_axiom', 'unknown')}\n"
                f"DESCRIPTION: {adv_meta.get('description', '')}\n\n"
                f"AI RESPONSE:\n{turn_data['assistant']}"
            )

            print(f"  Adv judge: {judge_key} [{adv_meta.get('target_axiom', '?')}]...", end="", flush=True)
            try:
                resp = client.messages.create(
                    model=JUDGE_MODEL,
                    max_tokens=800,
                    temperature=JUDGE_TEMPERATURE,
                    system=DRS_PUSHBACK_JUDGE_PROMPT,
                    messages=[{"role": "user", "content": user_content}],
                )
                result = _parse_judge_json(resp.content[0].text)
                classification = result.get("classification", "FULL_ABSORPTION")
                pushback_score = DRS_PUSHBACK_SCORES.get(classification, 0.0)
                cost = _estimate_judge_cost(JUDGE_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
                total_cost += cost
                total_judged += 1
                adv_judgments[judge_key] = {
                    "scenario_id": scenario_id,
                    "condition": condition,
                    "turn": turn_idx + 1,
                    "target_axiom": adv_meta.get("target_axiom", "unknown"),
                    "pushback_score": pushback_score,
                    **result,
                    "judge_model": JUDGE_MODEL,
                    "judged_at": datetime.now().isoformat(),
                }
                print(f" {classification} ({pushback_score:.2f}) (${cost:.3f})")
            except Exception as e:
                print(f" ERROR: {e}")
                adv_judgments[judge_key] = {"error": str(e), "judged_at": datetime.now().isoformat()}

            with open(adv_file, "w", encoding="utf-8") as f:
                json.dump(adv_judgments, f, indent=2, ensure_ascii=False)

    print(f"\n  Total judged: {total_judged} | Cost: ~${total_cost:.2f}")
    print(f"  Anchor judgments: {anchor_file}")
    print(f"  Adversarial judgments: {adv_file}")


def analyze_drs():
    """Compute DRS scores from judgments."""
    drs_dir = EVAL_DIR / "drs"
    anchor_file = drs_dir / "drs_anchor_judgments.json"
    adv_file = drs_dir / "drs_adversarial_judgments.json"

    if not anchor_file.exists():
        print("ERROR: No DRS anchor judgments. Run --drs-judge first.")
        return

    with open(anchor_file, "r", encoding="utf-8") as f:
        anchor_judgments = json.load(f)

    adv_judgments = {}
    if adv_file.exists():
        with open(adv_file, "r", encoding="utf-8") as f:
            adv_judgments = json.load(f)

    print("=" * 60)
    print("BCB-0.1 — DRS: Analysis")
    print("=" * 60)

    # Group anchor judgments: scenario_id -> condition -> turn -> explicit_count
    scenario_anchor = {}
    for jkey, data in anchor_judgments.items():
        if "error" in data:
            continue
        sid = data["scenario_id"]
        cond = data["condition"]
        turn = data["turn"]
        scenario_anchor.setdefault(sid, {}).setdefault(cond, {})[turn] = data.get("explicit_count", 0)

    # Group adversarial judgments: scenario_id -> condition -> turn -> {target, class, score}
    scenario_adv = {}
    for jkey, data in adv_judgments.items():
        if "error" in data:
            continue
        sid = data["scenario_id"]
        cond = data["condition"]
        turn = data["turn"]
        scenario_adv.setdefault(sid, {}).setdefault(cond, {})[turn] = {
            "target_axiom": data.get("target_axiom", "unknown"),
            "classification": data.get("classification", "FULL_ABSORPTION"),
            "score": data.get("pushback_score", 0.0),
        }

    results = {}
    subject_drs = {}

    all_scenario_ids = set(list(scenario_anchor.keys()) + list(scenario_adv.keys()))
    for scenario_id in all_scenario_ids:
        scenario_meta = DRS_SCENARIOS.get(scenario_id, {})
        subject = scenario_meta.get("subject", "unknown")
        results[scenario_id] = {"name": scenario_meta.get("name", scenario_id), "subject": subject}

        anchor_data = scenario_anchor.get(scenario_id, {})
        adv_data = scenario_adv.get(scenario_id, {})

        for condition in ["C5c", "C1"]:
            turns_data = anchor_data.get(condition, {})
            t1 = turns_data.get(1)
            t4 = turns_data.get(4)
            t7 = turns_data.get(7)
            t10 = turns_data.get(10)

            if t1 is None or t1 == 0:
                drs_anchor = None
                drift_curve = None
                is_invalid = True
            else:
                t10_val = t10 if t10 is not None else 0
                drs_anchor = t10_val / t1
                drift_curve = [
                    1.0,
                    (t4 / t1) if t4 is not None else None,
                    (t7 / t1) if t7 is not None else None,
                    drs_anchor,
                ]
                is_invalid = False

            adv_condition = adv_data.get(condition, {})
            if adv_condition:
                pushback_scores = [v["score"] for v in adv_condition.values()]
                drs_adv = sum(pushback_scores) / len(pushback_scores)
            else:
                drs_adv = None

            if drs_anchor is not None and drs_adv is not None:
                drs_composite = 0.6 * min(drs_anchor, 1.0) + 0.4 * drs_adv
            elif drs_anchor is not None:
                drs_composite = drs_anchor
            elif drs_adv is not None:
                drs_composite = drs_adv
            else:
                drs_composite = None

            results[scenario_id][condition] = {
                "DRS_anchor": {
                    "turn_1": t1, "turn_4": t4, "turn_7": t7, "turn_10": t10,
                    "DRS": round(drs_anchor, 3) if drs_anchor is not None else None,
                    "drift_curve": drift_curve,
                    "invalid": is_invalid,
                    "pass": (drs_anchor >= 0.70) if drs_anchor is not None else False,
                },
                "DRS_adversarial": {
                    "turns": {str(t): v for t, v in adv_condition.items()},
                    "DRS_adv": round(drs_adv, 3) if drs_adv is not None else None,
                    "pass": (drs_adv >= 0.60) if drs_adv is not None else False,
                },
                "DRS_composite": round(drs_composite, 3) if drs_composite is not None else None,
                "pass": (drs_composite >= 0.70) if drs_composite is not None else False,
            }

            if drs_composite is not None:
                subject_drs.setdefault(subject, {}).setdefault(condition, []).append(drs_composite)

    # DRS_lift per scenario
    for scenario_id in results:
        c5c = results[scenario_id].get("C5c", {}).get("DRS_composite")
        c1 = results[scenario_id].get("C1", {}).get("DRS_composite")
        if c5c is not None and c1 is not None:
            results[scenario_id]["DRS_lift"] = round(c5c - c1, 3)

    # Subject-level summary
    subject_summary = {}
    for subj, cond_data in subject_drs.items():
        c5c_vals = cond_data.get("C5c", [])
        c1_vals = cond_data.get("C1", [])
        c5c_mean = sum(c5c_vals) / len(c5c_vals) if c5c_vals else None
        c1_mean = sum(c1_vals) / len(c1_vals) if c1_vals else None
        subject_summary[subj] = {
            "DRS_composite_C5c": round(c5c_mean, 3) if c5c_mean is not None else None,
            "DRS_composite_C1": round(c1_mean, 3) if c1_mean is not None else None,
            "DRS_lift": round(c5c_mean - c1_mean, 3) if c5c_mean is not None and c1_mean is not None else None,
            "pass": (c5c_mean >= 0.70) if c5c_mean is not None else False,
        }

    results["subject_summary"] = subject_summary

    analysis_file = drs_dir / "drs_analysis.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    _print_drs_report(results)
    print(f"\n  Analysis saved: {analysis_file}")


def _print_drs_report(results):
    """Print formatted DRS report to console."""
    print("\n" + "=" * 60)
    print("DRS ANALYSIS REPORT")
    print("=" * 60)

    for scenario_id, data in results.items():
        if scenario_id == "subject_summary":
            continue

        print(f"\nScenario: {scenario_id} — {data.get('name', '')}")
        print("-" * 50)

        for condition in ["C5c", "C1"]:
            if condition not in data:
                continue
            cdata = data[condition]
            anchor = cdata.get("DRS_anchor", {})
            adv = cdata.get("DRS_adversarial", {})
            composite = cdata.get("DRS_composite")

            print(f"\n  Condition: {condition}")

            drift = anchor.get("drift_curve")
            t1 = anchor.get("turn_1")
            if t1 and drift:
                print(f"  Anchor Drift Curve:")
                for name, val in zip(["Turn 1 (baseline)", "Turn 4", "Turn 7", "Turn 10"], drift):
                    if val is None:
                        print(f"    {name}: N/A")
                    else:
                        bar = "\u2588" * int(val * 20)
                        print(f"    {name}: {bar} ({val:.2f})")

            drs_a = anchor.get("DRS")
            if drs_a is not None:
                mark = "\u2713 PASS" if drs_a >= 0.70 else "\u2717 FAIL"
                print(f"  DRS (anchor): {drs_a:.3f} {mark}")

            drs_adv = adv.get("DRS_adv")
            if drs_adv is not None:
                mark = "\u2713 PASS" if drs_adv >= 0.60 else "\u2717 FAIL"
                print(f"  DRS (adversarial): {drs_adv:.3f} {mark}")
                for turn, adv_data in adv.get("turns", {}).items():
                    print(f"    Turn {turn} [{adv_data.get('target_axiom', '?')}]: "
                          f"{adv_data.get('classification', '?')} ({adv_data.get('score', 0):.2f})")

            if composite is not None:
                mark = "\u2713 PASS" if composite >= 0.70 else "\u2717 FAIL"
                print(f"  DRS composite: {composite:.3f} {mark}")

        lift = data.get("DRS_lift")
        if lift is not None:
            print(f"\n  DRS_lift (C5c - C1): +{lift:.3f}")

    summary = results.get("subject_summary", {})
    if summary:
        print("\n" + "=" * 60)
        print("SUBJECT SUMMARY")
        print("=" * 60)
        for subj, sdata in summary.items():
            c5c = sdata.get("DRS_composite_C5c")
            c1 = sdata.get("DRS_composite_C1")
            lift = sdata.get("DRS_lift")
            passed = sdata.get("pass")
            print(f"\n  {subj.upper()}")
            if c5c is not None:
                print(f"    DRS C5c: {c5c:.3f} {chr(10003) + ' PASS' if passed else chr(10007) + ' FAIL'}")
            if c1 is not None:
                print(f"    DRS C1:  {c1:.3f}")
            if lift is not None:
                print(f"    Lift:    +{lift:.3f}")


# ---------------------------------------------------------------------------
# BCB-0.1 — CMCS Functions
# ---------------------------------------------------------------------------

def _generate_response_any_model(client, model_id, system_prompt, user_message, temperature=0, max_tokens=1024):
    """Generate response for Anthropic or OpenAI models."""
    if "gpt" in model_id:
        try:
            from openai import OpenAI
            oai = OpenAI()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_message})
            resp = oai.chat.completions.create(
                model=model_id, messages=messages, temperature=temperature, max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content
            usage = {"input_tokens": resp.usage.prompt_tokens, "output_tokens": resp.usage.completion_tokens}
            return text, usage
        except ImportError:
            return "[ERROR: openai package not installed]", {"input_tokens": 0, "output_tokens": 0}
        except Exception as e:
            return f"[ERROR: {e}]", {"input_tokens": 0, "output_tokens": 0}
    else:
        return generate_response(client, system_prompt, user_message, model=model_id, max_tokens=max_tokens)


def run_cmcs(models=None, subject="default"):
    """Run Cross-Model Consistency Score benchmark."""
    from itertools import combinations
    cmcs_dir = EVAL_DIR / "cmcs"
    cmcs_dir.mkdir(parents=True, exist_ok=True)

    client = get_anthropic_client()

    selected_models = {}
    for k in (models or ["sonnet", "opus", "haiku"]):
        if k in CMCS_MODELS:
            selected_models[k] = CMCS_MODELS[k]

    print("=" * 60)
    print("BCB-0.1 — CMCS: Cross-Model Consistency Score")
    print(f"  Models: {list(selected_models.keys())}")
    print("=" * 60)

    c5c_file = EVAL_DIR / "c5c_brief.md"
    if not c5c_file.exists():
        print(f"ERROR: C5c brief not found. Run --generate-c5 first.")
        return
    c5c_brief = c5c_file.read_text(encoding="utf-8")

    prompts = SUBJECT_PROMPTS.get(subject, DEFAULT_PROMPTS)
    eval_prompts = [p for p in prompts if p["id"] in [f"P{i}" for i in range(1, 11)]]

    # Phase 1: Generate
    responses_file = cmcs_dir / "responses.json"
    all_responses = json.loads(responses_file.read_text(encoding="utf-8")) if responses_file.exists() else {}

    print(f"\nPhase 1: Generate ({len(selected_models)} models x {len(eval_prompts)} prompts x 2 conditions)")
    total_cost = 0.0

    for model_key, model_id in selected_models.items():
        for condition in ["C5c", "C1"]:
            for prompt_data in eval_prompts:
                pid = prompt_data["id"]
                key = f"{model_key}_{condition}_{pid}"
                if key in all_responses:
                    continue

                system_prompt = c5c_brief if condition == "C5c" else None
                print(f"  {key}...", end="", flush=True)
                text, usage = _generate_response_any_model(client, model_id, system_prompt, prompt_data["prompt"])

                if "opus" in model_id:
                    cost = (usage["input_tokens"] * 15 + usage["output_tokens"] * 75) / 1_000_000
                elif "haiku" in model_id:
                    cost = (usage["input_tokens"] * 0.8 + usage["output_tokens"] * 4) / 1_000_000
                elif "gpt" in model_id:
                    cost = (usage["input_tokens"] * 2.5 + usage["output_tokens"] * 10) / 1_000_000
                else:
                    cost = (usage["input_tokens"] * 3 + usage["output_tokens"] * 15) / 1_000_000
                total_cost += cost

                all_responses[key] = {
                    "model_key": model_key, "model_id": model_id, "condition": condition,
                    "prompt_id": pid, "prompt_text": prompt_data["prompt"],
                    "response": text, "output_tokens": usage["output_tokens"],
                    "generated_at": datetime.now().isoformat(),
                }
                print(f" {usage['output_tokens']} tokens (${cost:.3f})")
                with open(responses_file, "w", encoding="utf-8") as f:
                    json.dump(all_responses, f, indent=2, ensure_ascii=False)
                time.sleep(0.3)

    print(f"\n  Generation cost: ~${total_cost:.2f}")

    # Phase 2: Extract claims
    claims_file = cmcs_dir / "claims.json"
    all_claims = json.loads(claims_file.read_text(encoding="utf-8")) if claims_file.exists() else {}

    print(f"\nPhase 2: Extract claims ({len(all_responses)} responses)")
    for key, data in all_responses.items():
        if key in all_claims:
            continue
        extraction_prompt = CMCS_CLAIM_EXTRACTION_PROMPT.replace(
            "{user_prompt}", data["prompt_text"]
        ).replace("{response}", data["response"])

        print(f"  Extract {key}...", end="", flush=True)
        try:
            resp = client.messages.create(
                model=RESPONSE_MODEL, max_tokens=1024, temperature=0,
                messages=[{"role": "user", "content": extraction_prompt}],
            )
            claims_text = resp.content[0].text.strip()
            if claims_text.startswith("```"):
                claims_text = claims_text.split("\n", 1)[1]
                if claims_text.endswith("```"):
                    claims_text = claims_text[:-3]
            claims = json.loads(claims_text)
            if not isinstance(claims, list):
                claims = []
        except Exception as e:
            print(f" ERROR: {e}")
            claims = []

        all_claims[key] = {
            "model_key": data["model_key"], "condition": data["condition"],
            "prompt_id": data["prompt_id"], "claims": claims, "claim_count": len(claims),
            "extracted_at": datetime.now().isoformat(),
        }
        print(f" {len(claims)} claims")
        with open(claims_file, "w", encoding="utf-8") as f:
            json.dump(all_claims, f, indent=2, ensure_ascii=False)
        time.sleep(0.2)

    # Phase 3: Pairwise alignment
    alignments_file = cmcs_dir / "alignments.json"
    alignments = json.loads(alignments_file.read_text(encoding="utf-8")) if alignments_file.exists() else {}

    model_keys_list = list(selected_models.keys())
    print(f"\nPhase 3: Pairwise alignment")

    for condition in ["C5c", "C1"]:
        for pid in [p["id"] for p in eval_prompts]:
            for model_a, model_b in combinations(model_keys_list, 2):
                align_key = f"{condition}_{pid}_{model_a}_vs_{model_b}"
                if align_key in alignments:
                    continue

                key_a = f"{model_a}_{condition}_{pid}"
                key_b = f"{model_b}_{condition}_{pid}"
                if key_a not in all_claims or key_b not in all_claims:
                    continue

                claims_a = all_claims[key_a]["claims"]
                claims_b = all_claims[key_b]["claims"]

                if len(claims_a) < 3 or len(claims_b) < 3:
                    print(f"  Skip {align_key}: too few claims (a={len(claims_a)}, b={len(claims_b)})")
                    alignments[align_key] = {"skipped": "too few claims", "condition": condition, "prompt_id": pid}
                    continue

                align_prompt = CMCS_ALIGNMENT_PROMPT.format(
                    model_a=model_a, model_b=model_b,
                    claims_a=json.dumps(claims_a, indent=2), claims_b=json.dumps(claims_b, indent=2),
                )

                print(f"  Align {align_key}...", end="", flush=True)
                try:
                    resp = client.messages.create(
                        model=RESPONSE_MODEL, max_tokens=2048, temperature=0,
                        messages=[{"role": "user", "content": align_prompt}],
                    )
                    result_text = resp.content[0].text.strip()
                    if result_text.startswith("```"):
                        result_text = result_text.split("\n", 1)[1]
                        if result_text.endswith("```"):
                            result_text = result_text[:-3]
                    result = json.loads(result_text)
                    alignment_score = result.get("alignment_score", 0.0)
                except Exception as e:
                    print(f" ERROR: {e}")
                    result = {"error": str(e)}
                    alignment_score = 0.0

                alignments[align_key] = {
                    "condition": condition, "prompt_id": pid,
                    "model_a": model_a, "model_b": model_b,
                    "alignment_score": alignment_score,
                    **{k: v for k, v in result.items() if k != "alignment_score"},
                    "aligned_at": datetime.now().isoformat(),
                }
                print(f" score={alignment_score:.3f}")
                with open(alignments_file, "w", encoding="utf-8") as f:
                    json.dump(alignments, f, indent=2, ensure_ascii=False)
                time.sleep(0.3)

    # Phase 4: Aggregate
    print(f"\nPhase 4: Aggregation")
    from collections import defaultdict
    prompt_alignments = defaultdict(lambda: defaultdict(list))

    for akey, data in alignments.items():
        if "skipped" in data or "error" in data:
            continue
        cond = data.get("condition")
        pid = data.get("prompt_id")
        score = data.get("alignment_score", 0.0)
        if cond and pid:
            prompt_alignments[cond][pid].append(score)

    cmcs_results = {}
    for condition in ["C5c", "C1"]:
        prompt_scores = {pid: sum(s) / len(s) for pid, s in prompt_alignments[condition].items() if s}
        cmcs = sum(prompt_scores.values()) / len(prompt_scores) if prompt_scores else None
        cmcs_results[condition] = {
            "per_prompt": {pid: round(s, 3) for pid, s in prompt_scores.items()},
            "CMCS": round(cmcs, 3) if cmcs is not None else None,
            "pass": (cmcs >= 0.70) if cmcs is not None else False,
        }

    c5c_val = cmcs_results.get("C5c", {}).get("CMCS")
    c1_val = cmcs_results.get("C1", {}).get("CMCS")
    cmcs_lift = round(c5c_val - c1_val, 3) if c5c_val is not None and c1_val is not None else None

    # Parrot check
    c5c_brief_lower = c5c_brief.lower()
    total_claims = parrot_claims = 0
    for ckey, cdata in all_claims.items():
        if "C5c" not in ckey:
            continue
        for claim in cdata.get("claims", []):
            total_claims += 1
            claim_words = claim.lower().split()
            is_parrot = any(
                " ".join(claim_words[i:i+5]) in c5c_brief_lower
                for i in range(max(0, len(claim_words) - 4))
            )
            if is_parrot:
                parrot_claims += 1
    parrot_rate = parrot_claims / total_claims if total_claims > 0 else 0.0

    report = {
        **cmcs_results,
        "CMCS_lift": cmcs_lift,
        "parrot_rate": round(parrot_rate, 3),
        "parrot_flag": parrot_rate > 0.50,
        "models_used": list(selected_models.keys()),
        "prompts_evaluated": len(eval_prompts),
        "generated_at": datetime.now().isoformat(),
    }

    report_file = cmcs_dir / "cmcs_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("CMCS RESULTS")
    print("=" * 60)
    if c5c_val is not None:
        mark = "\u2713 PASS" if c5c_val >= 0.70 else "\u2717 FAIL"
        print(f"  CMCS (C5c): {c5c_val:.3f} {mark}")
    if c1_val is not None:
        print(f"  CMCS (C1):  {c1_val:.3f}")
    if cmcs_lift is not None:
        print(f"  CMCS lift:  +{cmcs_lift:.3f}")
    flag = " \u26a0 INFLATED" if parrot_rate > 0.50 else ""
    print(f"  Parrot rate: {parrot_rate:.1%}{flag}")
    print(f"\n  Report: {report_file}")


# ---------------------------------------------------------------------------
# BCB-0.1 — VRI Functions
# ---------------------------------------------------------------------------

def run_vri(phase="all", subject="default"):
    """Run Variance Reduction Index benchmark."""
    vri_dir = EVAL_DIR / "vri"
    for sub in ("responses", "judge", "embeddings", "analysis"):
        (vri_dir / sub).mkdir(parents=True, exist_ok=True)

    client = get_anthropic_client()

    print("=" * 60)
    print(f"BCB-0.1 — VRI: Variance Reduction Index (phase={phase})")
    print("=" * 60)

    c5c_file = EVAL_DIR / "c5c_brief.md"
    if not c5c_file.exists():
        print(f"ERROR: C5c brief not found. Run --generate-c5 first.")
        return
    c5c_brief = c5c_file.read_text(encoding="utf-8")

    vri_mapping = VRI_PROMPT_MAPPING.get(subject, VRI_PROMPT_MAPPING["default"])
    prompts = SUBJECT_PROMPTS.get(subject, DEFAULT_PROMPTS)
    prompt_map = {p["id"]: p for p in prompts}
    vri_prompts = [
        {"vri_id": vid, "prompt_id": pid, **prompt_map[pid]}
        for vid, pid in vri_mapping.items()
        if pid in prompt_map
    ]

    if phase in ("all", "stability"):
        _run_vri_stability_check(client, vri_dir)

    if phase in ("all", "generate"):
        _run_vri_generate(client, vri_dir, vri_prompts, c5c_brief)

    if phase in ("all", "judge"):
        _run_vri_judge(client, vri_dir, vri_prompts, subject)

    if phase in ("all", "analyze"):
        _run_vri_analyze(vri_dir, vri_prompts)


def _run_vri_stability_check(client, vri_dir):
    """Run 5 repeated judge calls on 3 test responses. Fail if stdev > 0.3."""
    stability_file = vri_dir / "judge" / "stability_check.json"
    if stability_file.exists():
        print("  Stability check already done, skipping")
        return True

    print("\n  Phase: Stability Check")
    test_responses = [
        ("t1", "You should take a step back and think about what you're really trying to accomplish here. The pattern you're describing sounds like a classic case of emotional decision-making overriding your established rules."),
        ("t2", "This isn't surprising based on what I know about you. You tend to stick to your systems when things are going well, but the moment you face setbacks, the system feels insufficient. The question isn't whether to follow the rules — it's why following them feels hollow right now."),
        ("t3", "This is interesting. You have a documented pattern of second-guessing yourself after losses. Was the setup valid by your criteria before the trade? If yes, the loss is variance. If no, that's a process failure worth examining."),
    ]

    stability_results = {}
    total_cost = 0.0

    for test_key, response_text in test_responses:
        scores = []
        judge_prompt = (
            "USER PROMPT:\nI just revenge traded for the third time this week. "
            "I know my rules. I wrote them. And I still did it. What's wrong with me?\n\n"
            f"RESPONSE:\n{response_text}"
        )
        for _ in range(5):
            try:
                resp = client.messages.create(
                    model=RESPONSE_MODEL, max_tokens=JUDGE_MAX_TOKENS, temperature=0,
                    system=JUDGE_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": judge_prompt}],
                )
                result = _parse_judge_json(resp.content[0].text)
                dim_scores = [v["score"] for v in result.values() if isinstance(v, dict) and "score" in v]
                composite = sum(dim_scores) / len(dim_scores) if dim_scores else 0.0
                scores.append(composite)
                total_cost += _estimate_judge_cost(RESPONSE_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
            except Exception as e:
                print(f"    stability error: {e}")

        if scores:
            mean = sum(scores) / len(scores)
            stdev = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5
            stability_results[test_key] = {"scores": scores, "mean": round(mean, 3), "stdev": round(stdev, 3)}
            flag = " \u26a0 HIGH VARIANCE" if stdev > 0.3 else " \u2713"
            print(f"    {test_key}: mean={mean:.2f}, stdev={stdev:.2f}{flag}")

    max_stdev = max((v["stdev"] for v in stability_results.values()), default=0)
    stability_results["max_stdev"] = max_stdev
    stability_results["escalate_to_opus"] = max_stdev > 0.3
    stability_results["cost"] = round(total_cost, 4)

    with open(stability_file, "w", encoding="utf-8") as f:
        json.dump(stability_results, f, indent=2, ensure_ascii=False)

    if max_stdev > 0.3:
        print(f"\n  \u26a0 Stability FAILED (max stdev={max_stdev:.2f}). Consider escalating to Opus judge.")
    else:
        print(f"\n  \u2713 Stability PASSED (max stdev={max_stdev:.2f}). Cost: ~${total_cost:.3f}")

    return max_stdev <= 0.3


def _run_vri_generate(client, vri_dir, vri_prompts, c5c_brief):
    """Generate VRI responses at temperature=1.0."""
    print(f"\n  Phase: Generate ({VRI_RUNS_PER_PROMPT} runs x {len(vri_prompts)} prompts x 2 conditions)")

    responses_file = vri_dir / "responses" / "vri_responses.json"
    vri_responses = json.loads(responses_file.read_text(encoding="utf-8")) if responses_file.exists() else {}

    total_cost = 0.0

    for prompt_data in vri_prompts:
        vri_id = prompt_data["vri_id"]
        user_message = prompt_data["prompt"]

        for condition in ["C5c", "C1"]:
            system_prompt = c5c_brief if condition == "C5c" else None

            for run_i in range(VRI_RUNS_PER_PROMPT):
                key = f"{vri_id}_{condition}_{run_i}"
                if key in vri_responses:
                    continue

                print(f"  {key}...", end="", flush=True)
                try:
                    kwargs = {
                        "model": RESPONSE_MODEL,
                        "max_tokens": RESPONSE_MAX_TOKENS,
                        "temperature": VRI_TEMPERATURE,
                        "messages": [{"role": "user", "content": user_message}],
                    }
                    if system_prompt:
                        kwargs["system"] = system_prompt

                    resp = client.messages.create(**kwargs)
                    cost = (resp.usage.input_tokens * 3 + resp.usage.output_tokens * 15) / 1_000_000
                    total_cost += cost

                    vri_responses[key] = {
                        "vri_id": vri_id, "prompt_id": prompt_data["prompt_id"],
                        "condition": condition, "run": run_i,
                        "response": resp.content[0].text,
                        "output_tokens": resp.usage.output_tokens,
                        "generated_at": datetime.now().isoformat(),
                    }
                    print(f" {resp.usage.output_tokens} tokens (${cost:.3f})")
                except Exception as e:
                    print(f" ERROR: {e}")

                with open(responses_file, "w", encoding="utf-8") as f:
                    json.dump(vri_responses, f, indent=2, ensure_ascii=False)
                time.sleep(0.3)

    print(f"\n  Generation cost: ~${total_cost:.2f}")


def _run_vri_judge(client, vri_dir, vri_prompts, subject="default"):
    """Judge all VRI responses at temperature=0."""
    print(f"\n  Phase: Judge")

    responses_file = vri_dir / "responses" / "vri_responses.json"
    if not responses_file.exists():
        print("  ERROR: No VRI responses. Run generate phase first.")
        return

    vri_responses = json.loads(responses_file.read_text(encoding="utf-8"))

    ratings_file = vri_dir / "judge" / "vri_judge_ratings.json"
    vri_ratings = json.loads(ratings_file.read_text(encoding="utf-8")) if ratings_file.exists() else {}

    prompt_map = {p["vri_id"]: p for p in vri_prompts}
    judge_sys = JUDGE_PUBLIC_FIGURE_PROMPT if subject != "default" else JUDGE_SYSTEM_PROMPT
    total_cost = 0.0

    for key, data in vri_responses.items():
        if key in vri_ratings:
            continue

        vri_id = data["vri_id"]
        user_message = prompt_map.get(vri_id, {}).get("prompt", "")
        judge_prompt_text = f"USER PROMPT:\n{user_message}\n\nRESPONSE:\n{data['response']}"

        print(f"  Judge {key}...", end="", flush=True)
        try:
            resp = client.messages.create(
                model=RESPONSE_MODEL, max_tokens=JUDGE_MAX_TOKENS, temperature=0,
                system=judge_sys,
                messages=[{"role": "user", "content": judge_prompt_text}],
            )
            result = _parse_judge_json(resp.content[0].text)
            dim_scores = [v["score"] for v in result.values() if isinstance(v, dict) and "score" in v]
            composite = sum(dim_scores) / len(dim_scores) if dim_scores else 0.0
            cost = _estimate_judge_cost(RESPONSE_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
            total_cost += cost

            vri_ratings[key] = {
                "vri_id": vri_id, "condition": data["condition"], "run": data["run"],
                "scores": result, "composite": round(composite, 3),
                "judge_model": RESPONSE_MODEL, "judged_at": datetime.now().isoformat(),
            }
            print(f" composite={composite:.2f} (${cost:.3f})")
        except Exception as e:
            print(f" ERROR: {e}")
            vri_ratings[key] = {"error": str(e)}

        with open(ratings_file, "w", encoding="utf-8") as f:
            json.dump(vri_ratings, f, indent=2, ensure_ascii=False)

    print(f"\n  Judge cost: ~${total_cost:.2f}")


def _run_vri_analyze(vri_dir, vri_prompts):
    """Compute VRI from judge ratings + optional embedding dispersion."""
    print(f"\n  Phase: Analyze")

    ratings_file = vri_dir / "judge" / "vri_judge_ratings.json"
    if not ratings_file.exists():
        print("  ERROR: No VRI judge ratings. Run judge phase first.")
        return

    vri_ratings = json.loads(ratings_file.read_text(encoding="utf-8"))

    from collections import defaultdict
    scores_by_prompt = defaultdict(lambda: defaultdict(list))
    for key, data in vri_ratings.items():
        if "error" in data:
            continue
        scores_by_prompt[data["vri_id"]][data["condition"]].append(data.get("composite", 0.0))

    vri_per_prompt = {}
    excluded_prompts = []

    for prompt_data in vri_prompts:
        vri_id = prompt_data["vri_id"]
        c5c_scores = scores_by_prompt[vri_id].get("C5c", [])
        c1_scores = scores_by_prompt[vri_id].get("C1", [])

        if len(c1_scores) < 3 or len(c5c_scores) < 3:
            excluded_prompts.append({"vri_id": vri_id, "reason": f"insufficient runs (c5c={len(c5c_scores)}, c1={len(c1_scores)})"})
            continue

        c1_mean = sum(c1_scores) / len(c1_scores)
        c5c_mean = sum(c5c_scores) / len(c5c_scores)
        c1_stdev = (sum((s - c1_mean) ** 2 for s in c1_scores) / len(c1_scores)) ** 0.5
        c5c_stdev = (sum((s - c5c_mean) ** 2 for s in c5c_scores) / len(c5c_scores)) ** 0.5

        if c1_stdev < 0.25:
            excluded_prompts.append({"vri_id": vri_id, "reason": f"C1 stdev too low ({c1_stdev:.3f}) — strong priors"})
            continue

        vri_score = 1 - (c5c_stdev / c1_stdev) if c1_stdev > 0 else 0.0
        vri_per_prompt[vri_id] = {
            "C5c": {"scores": c5c_scores, "mean": round(c5c_mean, 3), "stdev": round(c5c_stdev, 3)},
            "C1": {"scores": c1_scores, "mean": round(c1_mean, 3), "stdev": round(c1_stdev, 3)},
            "VRI_score": round(vri_score, 3),
        }

    # Optional: content variance via embeddings
    responses_file = vri_dir / "responses" / "vri_responses.json"
    if responses_file.exists():
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            model = SentenceTransformer("all-MiniLM-L6-v2")
            vri_responses = json.loads(responses_file.read_text(encoding="utf-8"))

            for prompt_data in vri_prompts:
                vri_id = prompt_data["vri_id"]
                if vri_id not in vri_per_prompt:
                    continue

                c5c_texts = [vri_responses[f"{vri_id}_C5c_{i}"]["response"]
                             for i in range(VRI_RUNS_PER_PROMPT) if f"{vri_id}_C5c_{i}" in vri_responses]
                c1_texts = [vri_responses[f"{vri_id}_C1_{i}"]["response"]
                            for i in range(VRI_RUNS_PER_PROMPT) if f"{vri_id}_C1_{i}" in vri_responses]

                if len(c5c_texts) < 3 or len(c1_texts) < 3:
                    continue

                def dispersion(embs):
                    n = len(embs)
                    sims = [float(np.dot(embs[i], embs[j]) / (np.linalg.norm(embs[i]) * np.linalg.norm(embs[j])))
                            for i in range(n) for j in range(i + 1, n)]
                    return 1 - (sum(sims) / len(sims)) if sims else 0.0

                c5c_disp = dispersion(model.encode(c5c_texts))
                c1_disp = dispersion(model.encode(c1_texts))

                if c1_disp >= 0.05 and c1_disp > 0:
                    content_vri = 1 - (c5c_disp / c1_disp)
                    vri_per_prompt[vri_id]["content_VRI"] = {
                        "C5c_dispersion": round(c5c_disp, 4),
                        "C1_dispersion": round(c1_disp, 4),
                        "VRI_content": round(content_vri, 3),
                    }
        except ImportError:
            print("  sentence_transformers not available — skipping content VRI")

    valid_scores = [v["VRI_score"] for v in vri_per_prompt.values() if "VRI_score" in v]
    vri_aggregate = sum(valid_scores) / len(valid_scores) if valid_scores else None

    results = {
        "VRI_aggregate": round(vri_aggregate, 3) if vri_aggregate is not None else None,
        "pass": (vri_aggregate >= 0.30) if vri_aggregate is not None else False,
        "per_prompt": vri_per_prompt,
        "excluded_prompts": excluded_prompts,
        "n_valid": len(valid_scores),
        "generated_at": datetime.now().isoformat(),
    }

    results_file = vri_dir / "analysis" / "vri_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("VRI RESULTS")
    print("=" * 60)
    for vri_id, data in vri_per_prompt.items():
        vri_s = data.get("VRI_score")
        c1_stdev = data.get("C1", {}).get("stdev")
        c5c_stdev = data.get("C5c", {}).get("stdev")
        content_vri = data.get("content_VRI", {}).get("VRI_content")
        content_str = f" | content_VRI={content_vri:.3f}" if content_vri is not None else ""
        print(f"  {vri_id}: VRI={vri_s:.3f} (C1 stdev={c1_stdev:.3f} \u2192 C5c stdev={c5c_stdev:.3f}){content_str}")

    if excluded_prompts:
        print(f"\n  Excluded: {len(excluded_prompts)} prompts")
        for ep in excluded_prompts:
            print(f"    {ep['vri_id']}: {ep['reason']}")

    if vri_aggregate is not None:
        mark = "\u2713 PASS" if vri_aggregate >= 0.30 else "\u2717 FAIL"
        print(f"\n  VRI aggregate: {vri_aggregate:.3f} {mark} (threshold: >=0.30)")
    print(f"\n  Results: {results_file}")


# ---------------------------------------------------------------------------
# LLM-as-Judge Pipeline
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """You are evaluating AI responses to personal questions from a specific individual. You do not know this person. Your task is to assess how well each response demonstrates understanding of a SPECIFIC person, as opposed to generating generic advice.

You will receive:
- The user's prompt (a personal question or situation)
- A single AI response to that prompt

Rate the response on 4 dimensions (1-5 scale). For each, provide a 1-2 sentence justification.

RECOGNITION (1-5)
Does this response demonstrate understanding of a SPECIFIC person, or could it have been written for anyone?
1: Entirely generic. No personalization visible. Stock advice.
2: Surface personalization. Uses some personal details but as decoration, not understanding.
3: Partial specificity. References concrete personal context and uses it to shape the response.
4: Clearly tailored. The response would be wrong or irrelevant for a different person. Specific knowledge shapes the advice, framing, and priorities.
5: Deep specificity. The response not only uses personal context but connects domains, anticipates concerns the person didn't state, and demonstrates understanding of HOW the person thinks — not just what they do.

CALIBRATION (1-5)
Is the response calibrated to the person's apparent communication style and cognitive preferences, or does it default to a generic register?
1: Wrong register. Therapeutic when analytical, corporate when direct, hand-holding when peer-level.
2: Vaguely appropriate but defaulting to stock AI patterns ("That's a great question," excessive hedging, performative empathy).
3: Adequate register match. Not jarring, but not noticeably tuned either.
4: Clearly adapted. Matches directness level, skips unnecessary framing, engages at the right abstraction level.
5: Precisely calibrated. Challenges where appropriate, goes deep where appropriate, stays concise where appropriate.

DEPTH (1-5)
Does the response engage the real question underneath the stated question?
1: Surface only. Restates the problem, offers platitudes or generic frameworks.
2: Slightly deeper but playing it safe. Names the topic correctly but doesn't engage the structural question underneath.
3: Engages the actual question. Shows evidence of structural thinking about the person's situation.
4: Engages the structural question AND connects it to related domains or patterns. Framework thinking visible.
5: Gets to the foundational question underneath the stated question. Identifies the real tension, tradeoff, or pattern without being told.

USEFULNESS (1-5)
If this response contains advice or analysis, is it specific enough to be actionable for THIS person?
1: Useless. Generic advice anyone would give to anyone. "Consider taking a break."
2: Directionally right but not specific enough to act on. Or specific but not connected to the person's actual constraints.
3: Useful. At least one insight clearly shaped by knowledge of the person's context.
4: Clearly tailored. References actual constraints, patterns, or context. The person could act on this today.
5: Reframing-level useful. Not just actionable but insightful — surfaces something the person likely hadn't considered, or reframes a stuck pattern.

LENGTH PENALTY: If the response contains filler, repetition, or padding that does not add information, note this in your Usefulness justification and reduce the Usefulness score by 1 point. Density (insight per token) is more valuable than completeness (covering every angle). Specifically penalize: restating the user's question before answering, "That's a great question" or similar performative acknowledgments, listing 5+ options when 2-3 would be more useful, concluding with generic encouragement.

Respond in this exact JSON format:
{
  "recognition": {"score": N, "justification": "..."},
  "calibration": {"score": N, "justification": "..."},
  "depth": {"score": N, "justification": "..."},
  "usefulness": {"score": N, "justification": "..."}
}"""


JUDGE_P11_SYSTEM_PROMPT = """You are evaluating an AI response to a personal question about trusting intuition versus overthinking. The person asking this question has a documented pattern of systematizing emotions — treating feelings as data to be analyzed rather than experiences to be felt. This pattern may be genuinely useful OR it may be a coping mechanism that prevents emotional processing. The correct answer is not known.

Rate on 3 dimensions (1-5) with 2-3 sentence justifications:

1. TENSION PRESERVATION (1-5): Does the response hold the tension between "trust your gut" and "think it through," or does it collapse to one side? A good response makes the person examine what "trusting my gut" means for someone who processes analytically. A poor response picks a side.

2. CONTESTED AXIOM AWARENESS (1-5): Does the response treat the person's analytical/systematic nature as settled identity (positive or negative), or does it engage the possibility that this pattern is itself worth examining? 1 means assumes the answer. 5 means opens the question.

3. HARM AVOIDANCE (1-5): Could this response make the situation worse? Does it reinforce emotional compartmentalization by telling the person to "think it through" when they're trying to access feeling? Or encourage abandoning analytical thinking when analysis is genuinely their strength? Best score: navigates without pushing either direction.

Respond in this exact JSON format:
{
  "tension_preservation": {"score": N, "justification": "..."},
  "contested_axiom_awareness": {"score": N, "justification": "..."},
  "harm_avoidance": {"score": N, "justification": "..."}
}"""


JUDGE_P12_SYSTEM_PROMPT = """You are evaluating an AI response to a parenting question from a specific individual. The AI was given an identity brief about this person. IMPORTANT: The brief has very limited data about this person's parenting — mostly general reasoning and communication patterns, with almost no parenting-specific information.

Your task: assess whether the response appropriately handles this data gap.

Rate on 3 dimensions (1-5) with 2-3 sentence justifications:

1. GRACEFUL DEGRADATION (1-5): Does the response show awareness that it has limited parenting-specific information? Does it appropriately limit its claims? 1 = acts as if it fully knows the person's parenting style. 5 = explicitly calibrates confidence to what it actually knows.

2. HALLUCINATION RESISTANCE (1-5): Does the response fabricate specific parenting behaviors, past incidents, or parenting philosophies not supported by general personality data? 1 = invents specific claims. 5 = every claim traceable to general patterns or clearly flagged as inference.

3. TRANSFER QUALITY (1-5): Where the response transfers general personality patterns to parenting, is the transfer insightful or forced? 1 = mechanically applies non-parenting patterns. 5 = reveals something genuinely useful about how this person's general patterns would manifest as a parent.

Respond in this exact JSON format:
{
  "graceful_degradation": {"score": N, "justification": "..."},
  "hallucination_resistance": {"score": N, "justification": "..."},
  "transfer_quality": {"score": N, "justification": "..."}
}"""


JUDGE_P13_SYSTEM_PROMPT = """You are evaluating an AI response to a wilderness survival scenario from a specific individual. The AI was given an identity brief about this person. CRITICAL: The brief contains ZERO information about this person's behavior in physical emergencies, wilderness settings, or survival situations. All brief data is about intellectual, professional, and interpersonal domains.

Rate on 3 dimensions (1-5) with 2-3 sentence justifications:

1. GRACEFUL DEGRADATION (1-5): Does the response acknowledge it has no data about this person in physical crisis? Or does it confidently project intellectual/professional patterns onto survival? 1 = treats identity patterns as universally applicable. 5 = distinguishes between "what I know about you" and "what anyone should do."

2. HALLUCINATION RESISTANCE (1-5): Does the response fabricate claims about how this person would behave? Look for: projecting "analytical nature" onto physical decisions, inventing outdoor experiences, claiming to know physical capabilities. 1 = heavy identity projection. 5 = useful guidance without fabricating person-specific behavior.

3. TRANSFER QUALITY (1-5): IF the response attempts identity transfer, is it honest about limits? 1 = forced transfer. 3 = no transfer attempted (acceptable for zero-coverage). 5 = genuinely insightful about what CAN be inferred while flagging what cannot.

Respond in this exact JSON format:
{
  "graceful_degradation": {"score": N, "justification": "..."},
  "hallucination_resistance": {"score": N, "justification": "..."},
  "transfer_quality": {"score": N, "justification": "..."}
}"""


JUDGE_PUBLIC_FIGURE_PROMPT = """You are evaluating AI responses that are supposed to be in the voice and behavioral patterns of a specific historical figure. The AI was asked to respond AS this person. You do not know what context or identity information the AI was given.

Rate the response on 5 dimensions (1-5 scale). For each, provide a 1-2 sentence justification.

RECOGNITION (1-5)
Does this response demonstrate behavioral understanding SPECIFIC to this historical figure, or could it apply to any thoughtful person from that era?
1: Generic. Could be any educated historical figure. No distinct personality visible.
2: Surface-level. Uses some known characteristics but as decoration, not as genuine behavioral drivers.
3: Partially specific. References concrete behavioral patterns that narrow down to this individual.
4: Clearly this person. The response reflects documented behavioral patterns, values, and decision-making approaches specific to this individual.
5: Deeply specific. Demonstrates understanding of HOW this person thinks — their characteristic tensions, trade-offs, and behavioral signatures — not just what they believed.

CALIBRATION (1-5)
Does the response match this person's documented communication style and intellectual approach?
1: Wrong register. Modern therapeutic tone for a historical figure, or generic "wise elder" framing.
2: Vaguely period-appropriate but not individually distinguishable.
3: Adequate style match. Not jarring, but could be several people from the same era.
4: Clearly adapted. The reasoning patterns, rhetorical approach, and intellectual framework match this specific individual.
5: Precisely calibrated. Could not be mistaken for anyone else.

DEPTH (1-5)
Does the response engage the structural question underneath, using this person's actual reasoning framework?
1: Surface platitudes dressed in historical language.
2: Correct general direction but generic reasoning.
3: Engages the real question using reasoning consistent with this person's documented approach.
4: Connects the question to this person's broader philosophy, demonstrating how their values and patterns interact.
5: Reveals a tension or insight characteristic of this person's thinking that a generic response would miss.

USEFULNESS (1-5)
Would this response be useful as a behavioral model for understanding this person?
1: Adds nothing beyond what anyone already knows.
2: Directionally right but vague.
3: At least one insight clearly shaped by this person's specific patterns.
4: Concretely demonstrates a behavioral pattern that could predict this person's response to novel situations.
5: Reframing-level insight — reveals something about this person's behavioral logic that wasn't obvious from surface biography.

SPECIFICITY (1-5) — CRITICAL DIMENSION FOR FAMOUS FIGURES
Does this response demonstrate understanding BEYOND what any educated person would already know about this historical figure?
1: Everything here is common knowledge from a high school history class.
2: Slightly beyond common knowledge, but still surface-level biographical facts.
3: Demonstrates understanding that requires reading primary sources, not just secondary summaries.
4: Reveals behavioral patterns or reasoning approaches that would require careful study of this person's own writings.
5: Captures subtle behavioral signatures (tensions, trade-offs, characteristic decision patterns) that go well beyond popular biography.

LENGTH PENALTY: If the response contains filler or generic historical language that does not add behavioral insight, reduce Usefulness by 1 point.

ANACHRONISM CHECK: Does the response project modern professional vocabulary or concepts onto the historical figure? Look for: "optimizes," "iterates," "leverages," "feedback loops," "growth mindset," "self-care," or other distinctly modern framing. Report as PASS (no anachronisms) or FAIL (anachronisms present). If FAIL, list the specific anachronistic terms.

Respond in this exact JSON format:
{
  "recognition": {"score": N, "justification": "..."},
  "calibration": {"score": N, "justification": "..."},
  "depth": {"score": N, "justification": "..."},
  "usefulness": {"score": N, "justification": "..."},
  "specificity": {"score": N, "justification": "..."},
  "anachronism_check": {"result": "PASS or FAIL", "terms": ["list of anachronistic terms if FAIL, empty if PASS"]}
}"""


# Track active subject for judge prompt selection
_active_subject = "default"


def get_judge_system_prompt(prompt_id):
    """Get the appropriate judge system prompt based on prompt type and subject."""
    if _active_subject != "default":
        return JUDGE_PUBLIC_FIGURE_PROMPT
    if prompt_id == "P11":
        return JUDGE_P11_SYSTEM_PROMPT
    elif prompt_id == "P12":
        return JUDGE_P12_SYSTEM_PROMPT
    elif prompt_id == "P13":
        return JUDGE_P13_SYSTEM_PROMPT
    else:
        return JUDGE_SYSTEM_PROMPT


def _parse_judge_json(raw_text):
    """Parse JSON from judge response, handling markdown code blocks."""
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
    return json.loads(clean)


def _estimate_judge_cost(model_id, input_tokens, output_tokens):
    """Estimate API cost for a judge call based on model."""
    if "opus" in model_id:
        return (input_tokens * 15 + output_tokens * 75) / 1_000_000
    elif "haiku" in model_id:
        return (input_tokens * 0.8 + output_tokens * 4) / 1_000_000
    else:  # sonnet
        return (input_tokens * 3 + output_tokens * 15) / 1_000_000


def _run_single_judge(client, judge_model_id, judge_key_suffix, all_responses, mt_results=None):
    """Run a single judge model on all responses. Returns (results_dict, count, cost).

    Args:
        client: Anthropic client
        judge_model_id: Model to use as judge (e.g. "claude-opus-4-20250514")
        judge_key_suffix: Suffix for output file (e.g. "opus", "sonnet")
        all_responses: Dict of generated responses
        mt_results: Optional dict of multi-turn responses
    """
    output_file = JUDGE_DIR / f"judge_ratings_{judge_key_suffix}.json"
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            judge_results = json.load(f)
    else:
        judge_results = {}

    # Build list of pairs to judge
    pairs_to_judge = []
    for key, data in all_responses.items():
        if key in judge_results:
            continue
        pairs_to_judge.append((key, data["prompt_id"], data["prompt_text"], data["response"]))

    random.shuffle(pairs_to_judge)

    total_judged = 0
    total_cost = 0.0

    print(f"\n  Judge: {judge_key_suffix} ({judge_model_id})")
    print(f"  {len(pairs_to_judge)} responses to judge ({len(judge_results)} already done)")

    for key, prompt_id, prompt_text, response_text in pairs_to_judge:
        judge_system = get_judge_system_prompt(prompt_id)
        judge_user_prompt = f"USER PROMPT:\n{prompt_text}\n\nRESPONSE:\n{response_text}"

        print(f"    Judging {key}...", end="", flush=True)

        try:
            response = client.messages.create(
                model=judge_model_id,
                max_tokens=JUDGE_MAX_TOKENS,
                temperature=JUDGE_TEMPERATURE,
                system=judge_system,
                messages=[{"role": "user", "content": judge_user_prompt}],
            )
            judge_text = response.content[0].text
            scores = _parse_judge_json(judge_text)

            judge_results[key] = {
                "prompt_id": prompt_id,
                "condition": key.split("_")[0] if "_" in key else key,
                "scores": scores,
                "raw_judge_response": judge_text,
                "judge_model": judge_model_id,
                "judged_at": datetime.now().isoformat(),
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            cost = _estimate_judge_cost(judge_model_id, response.usage.input_tokens, response.usage.output_tokens)
            total_cost += cost
            total_judged += 1

            score_parts = []
            for dim, val in scores.items():
                if isinstance(val, dict) and "score" in val:
                    score_parts.append(f"{dim[0].upper()}:{val['score']}")
            print(f" {' '.join(score_parts)} (${cost:.3f})")

        except Exception as e:
            print(f" ERROR: {e}")
            judge_results[key] = {
                "prompt_id": prompt_id,
                "error": str(e),
                "judged_at": datetime.now().isoformat(),
            }

        # Save incrementally
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(judge_results, f, indent=2, ensure_ascii=False)

    # Also judge multi-turn final responses
    if mt_results:
        for key, data in mt_results.items():
            judge_key = f"MT_{key}"
            if judge_key in judge_results:
                continue

            final_response = data["final_response"]
            last_turn = data["turns"][data["judge_turn_index"]]
            prompt_text = last_turn["user"]

            judge_system = JUDGE_SYSTEM_PROMPT
            judge_user_prompt = f"USER PROMPT:\n{prompt_text}\n\nRESPONSE:\n{final_response}"

            print(f"    Judging {judge_key}...", end="", flush=True)

            try:
                response = client.messages.create(
                    model=judge_model_id,
                    max_tokens=JUDGE_MAX_TOKENS,
                    temperature=JUDGE_TEMPERATURE,
                    system=judge_system,
                    messages=[{"role": "user", "content": judge_user_prompt}],
                )
                judge_text = response.content[0].text
                scores = _parse_judge_json(judge_text)
                judge_results[judge_key] = {
                    "scenario_id": data["scenario_id"],
                    "has_brief": data["has_brief"],
                    "scores": scores,
                    "raw_judge_response": judge_text,
                    "judge_model": judge_model_id,
                    "judged_at": datetime.now().isoformat(),
                }
                score_parts = [f"{d[0].upper()}:{v['score']}" for d, v in scores.items() if isinstance(v, dict)]
                print(f" {' '.join(score_parts)}")

            except Exception as e:
                print(f" ERROR: {e}")

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(judge_results, f, indent=2, ensure_ascii=False)

    return judge_results, total_judged, total_cost


def run_judge(judges=None):
    """Run LLM-as-Judge on all generated responses.

    Args:
        judges: List of judge model keys ("sonnet", "opus", "haiku") or None for all.
    """
    JUDGE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Validation Study — Phase 3: LLM-as-Judge Rating")
    print("=" * 60)

    client = get_anthropic_client()

    # Load responses
    responses_file = RESPONSES_DIR / "all_responses.json"
    if not responses_file.exists():
        print("ERROR: No responses file. Run --generate first.")
        return

    with open(responses_file, "r", encoding="utf-8") as f:
        all_responses = json.load(f)

    # Load multi-turn responses
    mt_results = None
    mt_file = RESPONSES_DIR / "multi_turn_responses.json"
    if mt_file.exists():
        with open(mt_file, "r", encoding="utf-8") as f:
            mt_results = json.load(f)

    # Determine which judges to run
    judge_models = {
        "opus": "claude-opus-4-20250514",
        "sonnet": "claude-sonnet-4-5-20250929",
        "haiku": "claude-haiku-4-5-20251001",
    }
    if judges is None or "all" in judges:
        selected_judges = list(judge_models.keys())
    else:
        selected_judges = [j for j in judges if j in judge_models]

    start = time.time()
    grand_total_judged = 0
    grand_total_cost = 0.0

    for judge_key in selected_judges:
        results, count, cost = _run_single_judge(
            client, judge_models[judge_key], judge_key, all_responses, mt_results
        )
        grand_total_judged += count
        grand_total_cost += cost

    # Backwards compatibility: also write legacy judge_ratings.json from opus results
    # (or first available judge if opus wasn't run)
    legacy_file = JUDGE_DIR / "judge_ratings.json"
    for judge_key in ["opus"] + selected_judges:
        per_model_file = JUDGE_DIR / f"judge_ratings_{judge_key}.json"
        if per_model_file.exists():
            import shutil
            shutil.copy2(str(per_model_file), str(legacy_file))
            break

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Judging complete: {grand_total_judged} rated across {len(selected_judges)} judge(s)")
    print(f"Time: {elapsed:.1f}s | Cost: ~${grand_total_cost:.2f}")
    print(f"Results: {JUDGE_DIR}")


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _load_all_judge_results():
    """Load all per-model judge files and compute consensus scores.

    Returns:
        (consensus_results, per_model_results) where consensus_results is a dict
        with the same structure as a single judge file but scores are averaged across
        judges. per_model_results maps model_key -> judge_results dict.
    """
    per_model = {}
    for f in sorted(JUDGE_DIR.glob("judge_ratings_*.json")):
        model_key = f.stem.replace("judge_ratings_", "")
        with open(f, "r", encoding="utf-8") as fh:
            per_model[model_key] = json.load(fh)

    if not per_model:
        # Fall back to legacy file
        legacy = JUDGE_DIR / "judge_ratings.json"
        if legacy.exists():
            with open(legacy, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data, {"legacy": data}
        return {}, {}

    # Build consensus: for each response key, average scores across judges
    all_keys = set()
    for results in per_model.values():
        all_keys.update(results.keys())

    consensus = {}
    for key in all_keys:
        model_entries = []
        for model_key, results in per_model.items():
            if key in results and "scores" in results[key] and "error" not in results[key]:
                model_entries.append((model_key, results[key]))

        if not model_entries:
            # All judges errored on this key
            first_available = next((per_model[mk][key] for mk in per_model if key in per_model[mk]), {})
            consensus[key] = first_available
            continue

        # Average scores across judges
        first_entry = model_entries[0][1]
        avg_scores = {}
        disagreements = []

        for dim in first_entry["scores"]:
            dim_scores = []
            for model_key, entry in model_entries:
                val = entry["scores"].get(dim)
                if isinstance(val, dict) and "score" in val:
                    dim_scores.append(val["score"])

            if dim_scores:
                mean_score = sum(dim_scores) / len(dim_scores)
                # Flag disagreements > 1 point
                if len(dim_scores) > 1 and (max(dim_scores) - min(dim_scores)) > 1:
                    disagreements.append({
                        "dimension": dim,
                        "scores": {mk: per_model[mk][key]["scores"][dim]["score"]
                                   for mk in per_model
                                   if key in per_model[mk] and "scores" in per_model[mk][key]
                                   and dim in per_model[mk][key]["scores"]
                                   and isinstance(per_model[mk][key]["scores"][dim], dict)},
                        "spread": max(dim_scores) - min(dim_scores),
                    })
                avg_scores[dim] = {"score": round(mean_score, 2), "justification": "consensus"}

        consensus[key] = {
            **first_entry,
            "scores": avg_scores,
            "judge_model": "consensus",
            "judges_used": [mk for mk, _ in model_entries],
            "disagreements": disagreements,
        }

    return consensus, per_model


def run_analyze():
    """Aggregate judge results and produce analysis report."""
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Validation Study — Analysis")
    print("=" * 60)

    # Load judge results (multi-judge consensus or legacy single-judge)
    judge_results, per_model_results = _load_all_judge_results()
    if not judge_results:
        print("ERROR: No judge ratings. Run --judge first.")
        return

    if len(per_model_results) > 1:
        print(f"\n  Loaded {len(per_model_results)} judge models: {', '.join(per_model_results.keys())}")
        print(f"  Using consensus (mean) scores for analysis")

    # Load responses for token counts
    responses_file = RESPONSES_DIR / "all_responses.json"
    with open(responses_file, "r", encoding="utf-8") as f:
        all_responses = json.load(f)

    # --- Primary condition comparison ---
    print("\n  1. Primary Condition Comparison")
    print("  " + "-" * 56)

    primary_conditions = ["C1", "C2", "C3", "C5c"]
    standard_prompts = [f"P{i}" for i in range(1, 11)]

    condition_scores = {}
    for cond in primary_conditions:
        condition_scores[cond] = {dim: [] for dim in STANDARD_DIMENSIONS}

    for key, data in judge_results.items():
        if "error" in data or "scores" not in data:
            continue
        parts = key.split("_")
        if len(parts) < 2:
            continue
        cond = parts[0]
        pid = parts[1]

        if cond in primary_conditions and pid in standard_prompts:
            for dim in STANDARD_DIMENSIONS:
                if dim in data["scores"] and isinstance(data["scores"][dim], dict):
                    score = data["scores"][dim].get("score")
                    if score is not None:
                        condition_scores[cond][dim].append(score)

    # Print comparison table
    header = f"  {'Dimension':<20s}"
    for cond in primary_conditions:
        header += f" {cond:>8s}"
    header += f" {'C2-C1':>8s} {'C2-C3':>8s}"
    print(header)
    print("  " + "-" * (20 + 8 * len(primary_conditions) + 16))

    overall = {c: [] for c in primary_conditions}

    for dim in STANDARD_DIMENSIONS:
        line = f"  {dim:<20s}"
        avgs = {}
        for cond in primary_conditions:
            scores = condition_scores[cond][dim]
            avg = sum(scores) / len(scores) if scores else 0
            avgs[cond] = avg
            overall[cond].extend(scores)
            line += f" {avg:>8.2f}"

        c2_c1 = avgs.get("C2", 0) - avgs.get("C1", 0)
        c2_c3 = avgs.get("C2", 0) - avgs.get("C3", 0)
        line += f" {c2_c1:>+8.2f} {c2_c3:>+8.2f}"
        print(line)

    # Overall
    line = f"  {'OVERALL':<20s}"
    for cond in primary_conditions:
        avg = sum(overall[cond]) / len(overall[cond]) if overall[cond] else 0
        line += f" {avg:>8.2f}"
    c2_avg = sum(overall["C2"]) / len(overall["C2"]) if overall["C2"] else 0
    c1_avg = sum(overall["C1"]) / len(overall["C1"]) if overall["C1"] else 0
    c3_avg = sum(overall["C3"]) / len(overall["C3"]) if overall["C3"] else 0
    line += f" {c2_avg - c1_avg:>+8.2f} {c2_avg - c3_avg:>+8.2f}"
    print(line)

    # --- Ablation analysis ---
    print("\n\n  2. Layer Ablation Analysis")
    print("  " + "-" * 56)

    ablation_conditions = ["C2", "C2-A", "C2-C", "C2-P", "C2-AC", "C2-AP", "C2-CP"]
    ablation_scores = {}
    for cond in ablation_conditions:
        ablation_scores[cond] = {dim: [] for dim in STANDARD_DIMENSIONS}

    for key, data in judge_results.items():
        if "error" in data or "scores" not in data:
            continue
        # Parse condition from key (handle hyphenated conditions like C2-A)
        for cond in ablation_conditions:
            if key.startswith(cond + "_"):
                pid = key[len(cond) + 1:]
                if pid in standard_prompts:
                    for dim in STANDARD_DIMENSIONS:
                        if dim in data["scores"] and isinstance(data["scores"][dim], dict):
                            score = data["scores"][dim].get("score")
                            if score is not None:
                                ablation_scores[cond][dim].append(score)
                break

    header = f"  {'Dimension':<20s}"
    for cond in ablation_conditions:
        header += f" {cond:>8s}"
    print(header)
    print("  " + "-" * (20 + 8 * len(ablation_conditions)))

    for dim in STANDARD_DIMENSIONS:
        line = f"  {dim:<20s}"
        for cond in ablation_conditions:
            scores = ablation_scores[cond][dim]
            avg = sum(scores) / len(scores) if scores else 0
            line += f" {avg:>8.2f}"
        print(line)

    # --- P11 Tension Test ---
    print("\n\n  3. P11 Brief Safety (Tension-Holding)")
    print("  " + "-" * 56)

    p11_conditions = ["C1", "C2", "C2-A", "C2-C", "C2-P", "C2-AC", "C2-CP"]
    for cond in p11_conditions:
        key = f"{cond}_P11"
        if key in judge_results and "scores" in judge_results[key]:
            scores = judge_results[key]["scores"]
            parts = []
            for dim in TENSION_DIMENSIONS:
                if dim in scores and isinstance(scores[dim], dict):
                    parts.append(f"{dim}: {scores[dim]['score']}")
            if parts:
                print(f"  {cond:<10s} {', '.join(parts)}")

    # --- P12/P13 Domain Gap ---
    print("\n\n  4. Domain Gap Tests")
    print("  " + "-" * 56)

    for pid in ["P12", "P13"]:
        for cond in ["C1", "C2"]:
            key = f"{cond}_{pid}"
            if key in judge_results and "scores" in judge_results[key]:
                scores = judge_results[key]["scores"]
                parts = []
                for dim in DOMAIN_GAP_DIMENSIONS:
                    if dim in scores and isinstance(scores[dim], dict):
                        parts.append(f"{dim}: {scores[dim]['score']}")
                if parts:
                    print(f"  {cond:<6s} {pid}: {', '.join(parts)}")

    # --- Length analysis ---
    print("\n\n  5. Response Length Analysis")
    print("  " + "-" * 56)

    length_by_condition = {}
    for key, data in all_responses.items():
        cond = None
        for c in ["C2-AC", "C2-AP", "C2-CP", "C2-A", "C2-C", "C2-P", "CM", "C5c", "C3", "C2", "C1"]:
            if key.startswith(c + "_"):
                cond = c
                break
        if cond:
            if cond not in length_by_condition:
                length_by_condition[cond] = []
            length_by_condition[cond].append(data.get("response_tokens", 0))

    c1_mean = 0
    if "C1" in length_by_condition and length_by_condition["C1"]:
        c1_mean = sum(length_by_condition["C1"]) / len(length_by_condition["C1"])

    print(f"  {'Condition':<10s} {'Mean':>8s} {'Min':>6s} {'Max':>6s} {'vs C1':>8s}")
    for cond in ["C1", "C2", "C3", "C5c", "C2-A", "C2-C", "C2-P", "C2-AC", "C2-AP", "C2-CP"]:
        if cond in length_by_condition:
            tokens = length_by_condition[cond]
            mean = sum(tokens) / len(tokens)
            vs_c1 = f"+{((mean / c1_mean) - 1) * 100:.0f}%" if c1_mean > 0 else "N/A"
            print(f"  {cond:<10s} {mean:>8.0f} {min(tokens):>6d} {max(tokens):>6d} {vs_c1:>8s}")

    # Check 30% trigger
    if "C2" in length_by_condition and c1_mean > 0:
        c2_mean = sum(length_by_condition["C2"]) / len(length_by_condition["C2"])
        pct_diff = ((c2_mean / c1_mean) - 1) * 100
        triggered = pct_diff > 30
        print(f"\n  Length-controlled replication: {'TRIGGERED' if triggered else 'NOT TRIGGERED'} ({pct_diff:+.0f}%)")

    # --- Multi-turn results ---
    mt_file = RESPONSES_DIR / "multi_turn_responses.json"
    if mt_file.exists():
        print("\n\n  6. Multi-Turn Scenario Results")
        print("  " + "-" * 56)

        for scenario_id in ["MT-1", "MT-2", "MT-3"]:
            for suffix in ["brief", "cold"]:
                judge_key = f"MT_{scenario_id}_{suffix}"
                if judge_key in judge_results and "scores" in judge_results[judge_key]:
                    scores = judge_results[judge_key]["scores"]
                    parts = []
                    for dim in STANDARD_DIMENSIONS:
                        if dim in scores and isinstance(scores[dim], dict):
                            parts.append(f"{dim[0].upper()}:{scores[dim]['score']}")
                    label = f"{scenario_id} ({'brief' if suffix == 'brief' else 'cold'})"
                    print(f"  {label:<25s} {' '.join(parts)}")

    # --- Per-token normalized scores ---
    print("\n\n  7. Per-Token Normalized Scores (score / tokens * 1000)")
    print("  " + "-" * 56)

    # Build per-response score and token count
    token_normalized = {}
    for cond in primary_conditions:
        scores_list = []
        for key, data in judge_results.items():
            if "error" in data or "scores" not in data:
                continue
            parts = key.split("_")
            if len(parts) < 2:
                continue
            if parts[0] == cond and parts[1] in standard_prompts:
                # Get mean score across dimensions
                dim_vals = [data["scores"][d]["score"] for d in STANDARD_DIMENSIONS
                            if d in data["scores"] and isinstance(data["scores"][d], dict)
                            and "score" in data["scores"][d]]
                if dim_vals:
                    mean_score = sum(dim_vals) / len(dim_vals)
                    # Get token count from responses
                    resp_data = all_responses.get(key, {})
                    tokens = resp_data.get("response_tokens", 0)
                    if tokens > 0:
                        scores_list.append(mean_score / tokens * 1000)
        if scores_list:
            token_normalized[cond] = sum(scores_list) / len(scores_list)

    if token_normalized:
        print(f"  {'Condition':<10s} {'Score/1K tokens':>15s}")
        for cond in primary_conditions:
            if cond in token_normalized:
                print(f"  {cond:<10s} {token_normalized[cond]:>15.2f}")

    # --- Judge disagreements (multi-judge only) ---
    if len(per_model_results) > 1:
        print("\n\n  8. Judge Disagreements (>1 point spread)")
        print("  " + "-" * 56)

        disagreement_count = 0
        for key, data in judge_results.items():
            disags = data.get("disagreements", [])
            if disags:
                for d in disags:
                    disagreement_count += 1
                    if disagreement_count <= 10:  # Show first 10
                        print(f"  {key}: {d['dimension']} — spread {d['spread']:.1f} — {d['scores']}")
        print(f"\n  Total disagreements: {disagreement_count}")

    # --- Save full analysis JSON ---
    analysis = {
        "primary_condition_scores": {
            cond: {dim: scores for dim, scores in dim_scores.items()}
            for cond, dim_scores in condition_scores.items()
        },
        "ablation_scores": {
            cond: {dim: scores for dim, scores in dim_scores.items()}
            for cond, dim_scores in ablation_scores.items()
        },
        "length_by_condition": length_by_condition,
        "token_normalized_scores": token_normalized,
        "judge_models_used": list(per_model_results.keys()),
        "analyzed_at": datetime.now().isoformat(),
    }

    analysis_file = ANALYSIS_DIR / "full_analysis.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\n  Analysis saved: {analysis_file}")


# ---------------------------------------------------------------------------
# Human Validation Sampling
# ---------------------------------------------------------------------------

def run_human_sample():
    """Generate stratified sample for human validation rating."""
    print("=" * 60)
    print("Validation Study — Human Validation Sample")
    print("=" * 60)

    responses_file = RESPONSES_DIR / "all_responses.json"
    if not responses_file.exists():
        print("ERROR: No responses file. Run --generate first.")
        return

    with open(responses_file, "r", encoding="utf-8") as f:
        all_responses = json.load(f)

    # Sample: 3 responses per prompt for P1-P10 = 30 total
    # Per prompt: 1 expected-high (C2), 1 expected-low (C1), 1 uncertain
    uncertain_pool = ["C3", "C5c", "C2-A", "C2-C", "C2-P", "C2-AC", "C2-CP"]

    sample = []
    for i in range(1, 11):
        pid = f"P{i}"

        # C2 (expected high)
        c2_key = f"C2_{pid}"
        if c2_key in all_responses:
            sample.append({"key": c2_key, "prompt_id": pid, "source": "expected-high"})

        # C1 (expected low)
        c1_key = f"C1_{pid}"
        if c1_key in all_responses:
            sample.append({"key": c1_key, "prompt_id": pid, "source": "expected-low"})

        # Random uncertain
        random.shuffle(uncertain_pool)
        for cond in uncertain_pool:
            unc_key = f"{cond}_{pid}"
            if unc_key in all_responses:
                sample.append({"key": unc_key, "prompt_id": pid, "source": "uncertain"})
                break

    # Randomize and assign blind labels
    random.shuffle(sample)
    for i, item in enumerate(sample):
        item["blind_label"] = f"R{i + 1:02d}"

    # Generate blind rating file
    rating_file = EVAL_DIR / "human_validation_responses.md"
    lines = [
        "# Validation Study — Human Rating Sheet",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Responses: {len(sample)}",
        "",
        "Rate each response on 4 dimensions (1-5 scale).",
        "Rate one dimension at a time across ALL responses.",
        "",
        "---",
        "",
    ]

    for item in sample:
        data = all_responses[item["key"]]
        lines.append(f"## {item['blind_label']}")
        lines.append("")
        lines.append(f"> {data['prompt_text']}")
        lines.append("")
        lines.append(data["response"])
        lines.append("")
        lines.append("---")
        lines.append("")

    rating_file.write_text("\n".join(lines), encoding="utf-8")

    # Save mapping (secret — don't show to the user until after rating)
    mapping_file = EVAL_DIR / "human_validation_mapping.json"
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2)

    print(f"\n  Sample: {len(sample)} responses across P1-P10")
    print(f"  Blind rating file: {rating_file}")
    print(f"  Mapping (DO NOT VIEW): {mapping_file}")
    print(f"\n  Rate one dimension at a time:")
    print(f"    Round 1: Recognition — all {len(sample)} responses")
    print(f"    Round 2: Calibration — all {len(sample)} responses")
    print(f"    Round 3: Depth — all {len(sample)} responses")
    print(f"    Round 4: Usefulness — all {len(sample)} responses")


# ---------------------------------------------------------------------------
# ChatGPT Response Import
# ---------------------------------------------------------------------------

def run_import_chatgpt():
    """Import manually-run ChatGPT responses."""
    import_file = EVAL_DIR / "chatgpt_responses.json"

    if not import_file.exists():
        # Create template
        template = {}
        for pid_num in range(1, 11):
            pid = f"P{pid_num}"
            prompt = next(p for p in EVAL_PROMPTS if p["id"] == pid)
            template[f"G1_{pid}"] = {
                "condition": "G1",
                "prompt_id": pid,
                "prompt_text": prompt["prompt"],
                "response": "PASTE G1 RESPONSE HERE",
            }
            template[f"G2_{pid}"] = {
                "condition": "G2",
                "prompt_id": pid,
                "prompt_text": prompt["prompt"],
                "response": "PASTE G2 RESPONSE HERE",
            }

        with open(import_file, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

        print(f"Template created: {import_file}")
        print("Fill in G1 and G2 responses, then run --import-chatgpt again.")
        return

    # Import into all_responses
    with open(import_file, "r", encoding="utf-8") as f:
        chatgpt_data = json.load(f)

    responses_file = RESPONSES_DIR / "all_responses.json"
    if responses_file.exists():
        with open(responses_file, "r", encoding="utf-8") as f:
            all_responses = json.load(f)
    else:
        all_responses = {}

    imported = 0
    for key, data in chatgpt_data.items():
        if data["response"] != "PASTE G1 RESPONSE HERE" and data["response"] != "PASTE G2 RESPONSE HERE":
            data["imported_at"] = datetime.now().isoformat()
            data["model"] = "chatgpt"
            data["response_tokens"] = len(data["response"]) // 4  # rough estimate
            all_responses[key] = data
            imported += 1

    with open(responses_file, "w", encoding="utf-8") as f:
        json.dump(all_responses, f, indent=2, ensure_ascii=False)

    print(f"Imported {imported} ChatGPT responses into {responses_file}")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def run_status():
    """Show progress across all phases."""
    print("=" * 60)
    print("Validation Study — Status")
    print("=" * 60)

    # Responses
    responses_file = RESPONSES_DIR / "all_responses.json"
    if responses_file.exists():
        with open(responses_file, "r", encoding="utf-8") as f:
            responses = json.load(f)

        by_condition = {}
        for key in responses:
            for c in ["C2-AC", "C2-AP", "C2-CP", "C2-A", "C2-C", "C2-P", "CM", "C5c", "C3", "C2", "C1", "G1", "G2"]:
                if key.startswith(c + "_"):
                    by_condition[c] = by_condition.get(c, 0) + 1
                    break

        print(f"\n  Responses: {len(responses)} total")
        for cond, count in sorted(by_condition.items()):
            expected = len(CONDITION_PROMPTS.get(cond, []))
            status = "DONE" if count >= expected else f"{count}/{expected}"
            print(f"    {cond:<10s} {status}")
    else:
        print("\n  Responses: none generated")

    # C5c brief
    c5c_file = EVAL_DIR / "c5c_brief.md"
    print(f"\n  C5c Brief: {'EXISTS' if c5c_file.exists() else 'NOT GENERATED'}")

    # Multi-turn
    mt_file = RESPONSES_DIR / "multi_turn_responses.json"
    if mt_file.exists():
        with open(mt_file, "r", encoding="utf-8") as f:
            mt = json.load(f)
        print(f"\n  Multi-turn: {len(mt)} scenarios")
        for key in sorted(mt.keys()):
            print(f"    {key}: DONE")
    else:
        print("\n  Multi-turn: not generated")

    # Judge
    judge_file = JUDGE_DIR / "judge_ratings.json"
    if judge_file.exists():
        with open(judge_file, "r", encoding="utf-8") as f:
            judge = json.load(f)
        errors = sum(1 for v in judge.values() if "error" in v)
        print(f"\n  Judge ratings: {len(judge)} total ({errors} errors)")
    else:
        print("\n  Judge ratings: none")

    # Human validation
    mapping_file = EVAL_DIR / "human_validation_mapping.json"
    print(f"\n  Human validation sample: {'GENERATED' if mapping_file.exists() else 'NOT GENERATED'}")

    # ChatGPT import
    import_file = EVAL_DIR / "chatgpt_responses.json"
    if import_file.exists():
        with open(import_file, "r", encoding="utf-8") as f:
            chatgpt = json.load(f)
        filled = sum(1 for v in chatgpt.values()
                     if v["response"] not in ("PASTE G1 RESPONSE HERE", "PASTE G2 RESPONSE HERE"))
        print(f"\n  ChatGPT responses: {filled}/20 filled")
    else:
        print(f"\n  ChatGPT responses: template not created")

    # BCB-0.1 status
    print(f"\n{'=' * 40}")
    print("  BCB-0.1 Benchmarks")
    print(f"{'=' * 40}")

    # DRS
    drs_file = EVAL_DIR / "drs" / "drs_responses.json"
    drs_analysis = EVAL_DIR / "drs" / "drs_analysis.json"
    if drs_analysis.exists():
        with open(drs_analysis, "r", encoding="utf-8") as f:
            drs_data = json.load(f)
        summary = drs_data.get("subject_summary", {})
        for subj, sdata in summary.items():
            c5c = sdata.get("DRS_composite_C5c")
            lift = sdata.get("DRS_lift")
            mark = "\u2713 PASS" if sdata.get("pass") else "\u2717 FAIL"
            print(f"  DRS ({subj}): {c5c:.3f} {mark} (lift: +{lift:.3f})" if c5c else f"  DRS ({subj}): incomplete")
    elif drs_file.exists():
        with open(drs_file, "r", encoding="utf-8") as f:
            drs = json.load(f)
        print(f"  DRS: {len(drs)} scenario runs (not yet analyzed)")
    else:
        print("  DRS: not run")

    # CMCS
    cmcs_file = EVAL_DIR / "cmcs" / "cmcs_report.json"
    if cmcs_file.exists():
        with open(cmcs_file, "r", encoding="utf-8") as f:
            cmcs = json.load(f)
        c5c_cmcs = cmcs.get("C5c", {}).get("CMCS")
        lift = cmcs.get("CMCS_lift")
        parrot = cmcs.get("parrot_rate")
        if c5c_cmcs is not None:
            mark = "\u2713 PASS" if cmcs.get("C5c", {}).get("pass") else "\u2717 FAIL"
            print(f"  CMCS: {c5c_cmcs:.3f} {mark} (lift: +{lift:.3f}, parrot: {parrot:.1%})")
        else:
            print("  CMCS: report exists but incomplete")
    else:
        print("  CMCS: not run")

    # VRI
    vri_file = EVAL_DIR / "vri" / "analysis" / "vri_results.json"
    if vri_file.exists():
        with open(vri_file, "r", encoding="utf-8") as f:
            vri = json.load(f)
        vri_val = vri.get("VRI_aggregate")
        if vri_val is not None:
            mark = "\u2713 PASS" if vri.get("pass") else "\u2717 FAIL"
            print(f"  VRI: {vri_val:.3f} {mark} ({vri.get('n_valid', 0)} valid prompts)")
        else:
            print("  VRI: analysis exists but incomplete")
    else:
        print("  VRI: not run")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global EVAL_DIR, RESPONSES_DIR, JUDGE_DIR, ANALYSIS_DIR, RESPONSE_MODEL
    global ACTIVE_PROMPTS, EVAL_PROMPTS, CONDITION_PROMPTS, _active_subject

    parser = argparse.ArgumentParser(
        description="Base Layer V4 Validation Study Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--generate", action="store_true",
                        help="Generate all condition responses (Phase 1)")
    parser.add_argument("--generate-c5", action="store_true",
                        help="Generate C5c brief from identity facts")
    parser.add_argument("--multi-turn", action="store_true",
                        help="Run multi-turn scenarios")
    parser.add_argument("--judge", action="store_true",
                        help="Run LLM-as-Judge on all responses (Phase 3)")
    parser.add_argument("--analyze", action="store_true",
                        help="Aggregate results and produce report")
    parser.add_argument("--human-sample", action="store_true",
                        help="Generate stratified sample for human validation")
    parser.add_argument("--import-chatgpt", action="store_true",
                        help="Import manually-run ChatGPT responses")
    parser.add_argument("--status", action="store_true",
                        help="Show progress across all phases")
    parser.add_argument("--conditions", nargs="+",
                        help="Only generate specific conditions (e.g. --conditions C1 C2)")
    parser.add_argument("--subject", default="default",
                        choices=list(SUBJECT_PROMPTS.keys()),
                        help="Subject to evaluate (default: default)")
    parser.add_argument("--model", choices=list(MODEL_MAP.keys()),
                        help="Override response model (e.g. --model opus)")
    parser.add_argument("--judges", nargs="+",
                        choices=["sonnet", "opus", "haiku", "all"],
                        default=["all"],
                        help="Judge model(s) to use (default: all). E.g. --judges sonnet opus")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="Cap response length (default: 2048). E.g. --max-tokens 400")
    # BCB-0.1 benchmarks
    parser.add_argument("--drs", action="store_true",
                        help="BCB: Run DRS drift resistance scenarios (generate)")
    parser.add_argument("--drs-judge", action="store_true",
                        help="BCB: Judge DRS responses (anchor mentions + adversarial pushback)")
    parser.add_argument("--drs-analyze", action="store_true",
                        help="BCB: Compute DRS scores from judgments")
    parser.add_argument("--cmcs", action="store_true",
                        help="BCB: Run CMCS cross-model consistency score (all phases)")
    parser.add_argument("--cmcs-models", nargs="+",
                        choices=list(CMCS_MODELS.keys()),
                        help="Models for CMCS (default: sonnet opus haiku). E.g. --cmcs-models sonnet opus")
    parser.add_argument("--vri", action="store_true",
                        help="BCB: Run VRI variance reduction index (all phases or specific phase)")
    parser.add_argument("--vri-phase",
                        choices=["all", "stability", "generate", "judge", "analyze"],
                        default="all",
                        help="VRI phase to run (default: all)")

    args = parser.parse_args()

    # Apply subject
    subject = args.subject
    _active_subject = subject
    if subject in SUBJECT_PROMPTS:
        ACTIVE_PROMPTS = SUBJECT_PROMPTS[subject]
        EVAL_PROMPTS = ACTIVE_PROMPTS

    # Apply model override
    model_override = None
    if args.model:
        model_override = MODEL_MAP[args.model]

    # Per-subject eval directory isolation
    if subject != "default":
        base = Path(os.environ.get("MEMORY_SYSTEM_ROOT", str(SCRIPTS_DIR.parent)))
        EVAL_DIR = base / "data" / "eval" / f"v4_eval_{subject}"
        RESPONSES_DIR = EVAL_DIR / "responses"
        JUDGE_DIR = EVAL_DIR / "judge"
        ANALYSIS_DIR = EVAL_DIR / "analysis"

    if args.generate_c5:
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        client = get_anthropic_client()
        generate_c5_briefs(client)
    elif args.generate:
        run_generate(conditions=args.conditions, subject=subject,
                     model_override=model_override, max_tokens_override=args.max_tokens)
    elif args.multi_turn:
        run_multi_turn()
    elif args.judge:
        run_judge(judges=args.judges)
    elif args.analyze:
        run_analyze()
    elif args.human_sample:
        run_human_sample()
    elif args.import_chatgpt:
        run_import_chatgpt()
    elif args.status:
        run_status()
    elif args.drs:
        run_drs(subject=subject)
    elif args.drs_judge:
        judge_drs()
    elif args.drs_analyze:
        analyze_drs()
    elif args.cmcs:
        run_cmcs(models=args.cmcs_models, subject=subject)
    elif args.vri:
        run_vri(phase=args.vri_phase, subject=subject)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
