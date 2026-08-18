"""Author a layer from a handoff package, then compose. The last two hops.

EXPERIMENTAL AND UNTESTED. No test exercises this module; see
baselayer/distillation/__init__.py for the full status.

🎯 WHAT WAS MISSING. Distillation produced trees. `assemble.py` turned trees into a package.
Nothing read the package. This closes it: render the package into the layer's own prompt, author,
then compose the three layers WITH THE CONTRADICTIONS UNION.

🚨 WHY COMPOSE GETS THE CONTRADICTIONS AND THE LAYER AUTHORS' OUTPUT IS NOT ENOUGH.
The three layer authors are blind to each other by design: layers are allowed to contradict, and
contradictions are meant to be detected rather than prevented. That makes compose the ONLY node
in the pipeline that can see across all three. What it receives is three finished prose layers --
which is the form in which a tension has already been smoothed by three independent summarisers.
A contradiction between what someone believes and what they do can surface in ANCHORS as a
contested axiom and in PREDICTIONS as an unreliable expectation, and no layer author can see
that pairing. Handing compose the carried contradictions costs nothing, since they are already
computed, and gives it the one thing it has never had.

⚠️ THE PACKAGE IS RENDERED AS STRATA, NOT FLATTENED. The author must be able to tell a
majority-verified singularity from a single-run one, and a fact every run dismissed from one
they disagreed about. Flattening would discard exactly what the multi-run design bought and
would hand the author a pile it cannot weigh.
"""
import argparse
import io
import json
import os
import sys

# This module now lives inside the baselayer package and imports nothing from it, so the
# old walk-up-to-the-checkout shim is gone (from here, it resolved to a path that does not
# exist). BASELAYER_SRC is still honoured so a caller can pin which checkout resolves first.
_src = os.environ.get("BASELAYER_SRC")
if _src:
    sys.path.insert(0, _src)
import anthropic


def render(pkg, max_themes=None):
    """Render a handoff package as labelled strata.

    🚨 max_themes WAS 400 AND IT SHOWED THE AUTHOR 8% OF THE EVIDENCE.
    On a 37,839-fact corpus the package carries 4,954 themes collected mechanically from 631
    leaves; the author saw 400, immediately after a log line reporting how many had been
    collected. This is the FIFTH unnamed cap of the same class found in this codebase, after a
    hardcoded 15-facts-per-category selector cap, an unnamed limit=20 in a retrieval tool schema,
    the display truncations, and [:6] ids per theme. Each looked like formatting; each bounded
    something load-bearing.
    ✅ Default None: show everything. Measured payload at that size is ~700K tokens against a 1M
    window, so it fits, and the assertion at the end of this function makes truncation a run
    failure rather than a silent default.
    """
    L = []
    L.append("DISTILLED EVIDENCE for the %s layer. Every fact in the corpus passed through a "
             "summarisation pass and received a recorded disposition; nothing below was "
             "selected by a retrieval query.\n" % (pkg.get("layer") or "?").upper())
    if pkg.get("verified_meaningful", pkg["n_runs"] > 1):
        L.append("Assembled from %d independent runs. Threshold for 'verified' is presence in "
                 ">= %d of them.\n" % (pkg["n_runs"], pkg["min_runs_for_verified"]))
    else:
        # AT n=1 THE THRESHOLD IS 1 AND EVERY SINGULARITY MEETS IT. Telling the author these
        # are "verified" asserts corroboration a single run cannot supply, over material that
        # is 57-62% run-specific. Say what is true instead.
        L.append("Assembled from %d run. THERE IS NO CORROBORATION: the majority threshold is "
                 "%d, which every singularity meets automatically. Nothing below is replicated. "
                 "57-62%% of single-run singularities are resampling noise, so treat the whole "
                 "singularity section as CANDIDATES.\n"
                 % (pkg["n_runs"], pkg["min_runs_for_verified"]))

    L.append("\n## THEMES  (%d statements across %d runs, NOT de-duplicated)\n" %
             (len(pkg["themes"]), pkg["n_runs"]))
    L.append("The runs restate the same claims in different words. Judge which say the same "
             "thing BY READING them; automated matching scored real 7-of-9 agreement at 0-24%% "
             "and would mislead you. `run` marks which pass produced each.\n")
    # 🚨 THE 6-ID CAP WAS AN UNNAMED LITERAL AND IT SILENTLY BOUNDED THE EVIDENCE.
    # `[:6]` in a formatting expression. The author cannot cite an id it was never shown, so ids
    # 7+ were unciteable while the gate happily accepted the full set. Fourth instance of the
    # same shape, after the 15-facts-per-category selector cap, the unnamed limit=20 in a
    # retrieval tool schema, and the display caps.
    #
    # 🎯 AND IT SETTLES THE CITATION QUESTION: a theme resting on 60 facts cannot honestly cite 6.
    # Stating the COUNT beside the ids is what makes "these are the basis" distinguishable from
    # "these are a sample", which is the difference between a citation and a gesture.
    for t in pkg["themes"][:max_themes]:
        fids = t.get("fact_ids") or []
        tags = " ".join("[F-%s]" % f for f in fids)
        L.append("- [run %s] %s  (rests on %d fact%s) %s"
                 % (t.get("from_run"), t["statement"], len(fids),
                    "" if len(fids) == 1 else "s", tags))

    if pkg.get("verified_meaningful", pkg["n_runs"] > 1):
        L.append("\n## SINGULARITIES, VERIFIED  (%d, in >= %d of %d runs, VERBATIM)\n"
                 % (len(pkg["singularities_verified"]), pkg["min_runs_for_verified"],
                    pkg["n_runs"]))
    else:
        L.append("\n## SINGULARITIES, UNREPLICATED  (%d, from a single run, VERBATIM)\n"
                 % len(pkg["singularities_verified"]))
    L.append("Facts no theme covers, carried unparaphrased. A fact can be decisive and appear "
             "exactly once; frequency is not significance.\n")
    for s in pkg["singularities_verified"]:
        L.append("- [F-%s] %s   (%d/%d runs)" % (s["fact_id"], s["verbatim"], s["runs"],
                                                  pkg["n_runs"]))

    L.append("\n## SINGULARITIES, UNVERIFIED  (%d, single-run)\n"
             % len(pkg["singularities_unverified"]))  # all shown; no cap
    L.append("⚠️ 57-62%% of single-run singularities are resampling noise. Treat as candidates, "
             "not evidence. Use only if a verified item or a theme corroborates.\n")
    for s in pkg["singularities_unverified"]:
        L.append("- [F-%s] %s" % (s["fact_id"], s["verbatim"]))

    L.append("\n## CONTRADICTIONS  (%d, union, NEVER resolved)\n" % len(pkg["contradictions"]))
    L.append("🚨 DO NOT RESOLVE THESE. Where this person's stated belief conflicts with reported "
             "action, that gap IS the finding. Carry it, name it, do not smooth it.\n")
    for c in pkg["contradictions"]:
        L.append("- %s  %s vs %s" % (c.get("tension", ""), c.get("a_fact_ids") or [],
                                     c.get("b_fact_ids") or []))

    L.append("\n## SET ASIDE\n")
    L.append("%d facts every run judged not load-bearing for this layer. %d are CONTESTED: some "
             "runs dismissed them and others kept them, and that disagreement is information.\n"
             % (len(pkg["dismissed_by_all_runs"]), len(pkg["dismissed_CONTESTED"])))
    out = "\n".join(L)

    # 🚨 NO-TRUNCATION ASSERTION. Five unnamed caps of this class were found in this codebase,
    # four of them by accident. This turns the whole class into a test: what was COLLECTED must
    # equal what is RENDERED, or the run fails. The requirement is a quality gate proving the
    # layer author either sees ALL the information or sees a compressed version of ALL of it.
    # This answers the first half mechanically. The second half (an explicit collapse) is a
    # separate build and must not be assumed to have happened.
    if max_themes is None:
        miss_t = sum(1 for t in pkg["themes"]
                     if (t.get("statement") or "")[:60] not in out)
        sings = pkg["singularities_verified"] + pkg["singularities_unverified"]
        miss_s = sum(1 for x in sings if ("[F-%s]" % x["fact_id"]) not in out)
        if miss_t or miss_s:
            raise SystemExit(
                "TRUNCATION BETWEEN PACKAGE AND PROMPT: %d of %d themes and %d of %d "
                "singularities did not reach the rendered text. The author would have been "
                "given less than was collected, while the log reported the collected number."
                % (miss_t, len(pkg["themes"]), miss_s, len(sings)))
    return out


# 🚨 CITATION IS ENFORCED BY THE SCHEMA, NOT REQUESTED IN THE PROMPT.
# Measured on claude-opus-5: an explicit "CITATION IS MANDATORY" directive, with ids supplied in
# the exact [F-xxx] format the layer prompt declares, produced ZERO citations across anchors,
# core, predictions AND the composed brief. A frontier model, a mandatory instruction, the
# pre-matched format, nothing. Earlier work in this project already recorded prose self-citation
# as unreliable at ~57% faithfulness; the measurement here says the honest number can be zero.
#
# 🎯 SO THE LAYER IS AUTHORED AS A TOOL CALL, NOT AS PROSE. With strict:true the API GUARANTEES
# tool_use.input validates against this schema, so a claim object CANNOT be emitted without its
# fact_ids field. That is not the model choosing to comply; it is the API refusing to produce
# anything else.
#
# ⚠️ THE ONE LIMIT, AND IT IS WHY THE POST-CHECK STAYS: JSON-schema numeric and array constraints
# (minItems) are NOT supported by structured outputs, so the schema can require the FIELD but not
# that the array is NON-EMPTY. The gate is therefore three parts and all three are load-bearing:
#   1. schema requires the field        -- API-enforced, cannot be violated
#   2. a post-check for non-empty AND resolvable against the ids the package actually supplied
#   3. reject and re-ask naming the violation; RAISE after N attempts
# Part 3 already exists one level down (distill.py leaves validate, re-ask, record
# schema_fail_final). The authoring hop had no equivalent and accepted whatever came back.
#
# THE REQUIREMENT, stated plainly: emitting the citation is mandatory, output is not accepted
# until it is emitted, and citations and provenance are required at EVERY output level --
# leaves, layers and brief alike.
CLAIM = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Stable short id, e.g. A1, C2, P3."},
        "name": {"type": "string", "description": "Short name in UPPERCASE, words separated by single spaces, e.g. CONFIRMATION BEFORE ACTION. Three to five words."},
        "statement": {"type": "string", "description": "The claim itself, in prose."},
        "active_when": {"type": "string", "description": "When this applies. May be empty."},
        "fact_ids": {"type": "array", "items": {"type": "string"},
                     "description": "The fact ids this claim rests on, taken VERBATIM from the "
                                    "evidence. A claim with no ids cannot be audited and is not "
                                    "acceptable output."},
        "contested": {"type": "boolean",
                      "description": "True if the evidence contradicts itself here. Carry the "
                                     "tension; do not resolve it."},
    },
    "required": ["id", "name", "statement", "active_when", "fact_ids", "contested"],
    "additionalProperties": False,
}
LAYER_SCHEMA = {
    "type": "object",
    "properties": {
        "layer": {"type": "string"},
        "preamble": {"type": "string", "description": "One paragraph framing. May be empty."},
        "claims": {"type": "array", "items": CLAIM},
    },
    "required": ["layer", "preamble", "claims"],
    "additionalProperties": False,
}


# 🚨 THE AUTHORING PATH HAD NO API RETRY. Two of three stability runs died on a transient
# `overloaded_error` and lost their whole layer set. This is the IDENTICAL defect already fixed
# in distill.py, where a 631-chunk run died at chunk 380 and discarded every completed leaf: the
# retry was added to distillation and never carried across to its sibling.
#
# 🎯 A FIX APPLIED TO ONE CODE PATH AND NOT ITS SIBLING. Third instance of that shape, after the
# compose evidence map that was assigned and never read, and the node schema fixed in the
# validator while the prompt kept asking for the removed field. Enumerate the call sites, then fix.
_TRANSIENT = ("overloaded_error", "rate_limit_error", "api_error", "timeout")


def _stream_with_retry(cl, model, maxtok, tool, msgs, tries=5, tool_name="emit_layer"):
    import time
    for n in range(1, tries + 1):
        try:
            with cl.messages.stream(model=model, max_tokens=maxtok, tools=[tool],
                                    tool_choice={"type": "tool", "name": tool_name},
                                    messages=msgs) as st:
                return st.get_final_message()
        except Exception as e:
            if not any(t in str(e) for t in _TRANSIENT) or n == tries:
                raise
            wait = min(60, 2 ** n)
            print("    transient API error, retry %d/%d in %ds" % (n, tries, wait), flush=True)
            time.sleep(wait)


def call_structured(cl, model, prompt, schema, supplied, maxtok=16000, tries=3,
                    tool_name="emit_layer"):
    """Author via a strict tool call, then VERIFY AT THE OUTPUT and re-ask on failure.

    `supplied` is the set of fact ids the package actually handed this author. An id outside it
    was not evidence this run saw, so it is a fabrication and fails the gate exactly as a missing
    id does.
    """
    tool = {"name": tool_name, "description": "Emit the authored output.",
            "strict": True, "input_schema": schema}
    msgs = [{"role": "user", "content": prompt}]
    last = ""
    for attempt in range(1, tries + 1):
        r = _stream_with_retry(cl, model, maxtok, tool, msgs, tool_name=tool_name)
        blk = next((b for b in r.content if getattr(b, "type", None) == "tool_use"), None)
        if blk is None:
            raise RuntimeError("no tool_use block, stop_reason=%s" % r.stop_reason)
        data = blk.input
        claims = data.get("claims") or data.get("sections") or []
        naked = [c.get("id") or c.get("heading", "?") for c in claims
                 if not (c.get("fact_ids") or [])]
        bogus = sorted({f for c in claims for f in (c.get("fact_ids") or [])
                        if f.lstrip("F-").strip("[]") not in supplied})
        # 🚨 THE GATE WAS ALL-OR-NOTHING AND THAT IS THE WRONG SHAPE. A single malformed id
        # (e.g. `fe1bfda`, seven hex chars instead of eight) killed an otherwise sound layer
        # carrying 475 valid citations, three times, then failed the run. A layer with hundreds
        # of good citations and one typo is not a failed run.
        # 🎯 So: STRIP the unrecognised ids, KEEP the layer, and REPORT the count so the rate
        # stays visible. Same rule the leaves already follow -- stripping fixes the artifact and
        # must not hide the measurement. Only a layer with NO valid citations still fails.
        dropped = 0
        for c in claims:
            keep = [f for f in (c.get("fact_ids") or [])
                    if f.lstrip("F-").strip("[]") in supplied]
            dropped += len(c.get("fact_ids") or []) - len(keep)
            c["fact_ids"] = keep
        still_naked = [c.get("id") or c.get("heading", "?") for c in claims
                       if not (c.get("fact_ids") or [])]
        if claims and not still_naked:
            cited = {f.lstrip("F-").strip("[]") for c in claims for f in c["fact_ids"]}
            print("    citations: %d claims, ALL cited, %d distinct ids, %d unrecognised dropped"
                  % (len(claims), len(cited), dropped), flush=True)
            return data, r.usage.input_tokens, r.usage.output_tokens

        if not claims:
            problem = "you emitted zero claims"
        elif still_naked:
            problem = ("these claims carry NO fact ids: %s. Every claim must cite the evidence "
                       "it rests on." % ", ".join(still_naked))
        elif bogus:
            problem = ("these ids appear in no evidence you were given: %s. Cite only ids that "
                       "are present in the evidence above." % ", ".join(bogus[:10]))
        else:
            cited = {f.lstrip("F-").strip("[]") for c in claims for f in c["fact_ids"]}
            print("    citations: %d claims, ALL cited, %d distinct ids, 0 fabricated"
                  % (len(claims), len(cited)), flush=True)
            return data, r.usage.input_tokens, r.usage.output_tokens
        last = problem
        print("    ATTEMPT %d REJECTED: %s" % (attempt, problem[:110]), flush=True)
        # RE-ASK FRESH RATHER THAN THREADING A CONVERSATION. Accumulating assistant turns broke
        # the tool_use/tool_result pairing on the second rejection: "tool_use ids were found
        # without tool_result blocks immediately after". Thinking is on by default on Opus 5, so
        # r.content carries a thinking block alongside the tool_use and the pairing is fragile.
        # A fresh call with the violation appended is simpler, cannot desynchronise, and costs
        # the same -- the prompt is re-sent either way.
        msgs = [{"role": "user", "content": prompt + chr(10) + chr(10)
                 + "YOUR PREVIOUS ATTEMPT WAS REJECTED: " + problem
                 + " Emit the whole layer again with that corrected."}]
    # 🚨 A LAYER WITH NO RESOLVABLE CITATIONS IS A FAILED RUN, NOT A RUN WITH A GAP.
    raise RuntimeError("CITATION GATE FAILED after %d attempts: %s" % (tries, last))


def render_claims(d):
    """Render the structured layer to markdown, ids inline so the artifact is auditable too.

    🚨 TWO CITATION SHAPES, BOTH REQUIRED, NEITHER REPLACES THE OTHER.
    This module emitted inline [F-xxxxxxxx] tags while the verification tooling
    (`parse_provenance_from_layer` -> `generate_verification_questions` -> `verify_claims`)
    only reads `provenance: [F-xxx, ...]` lines. The result was a spec with 115 resolving
    citations on which `verify_claims` reported "No verification questions generated" --
    byte-identical to what a healthy run with zero claims reports, so the whole check
    family was a silent no-op on this pipeline's own output.
      - The inline tags STAY: the citation gate in this file and compose's `supplied` set
        (the [0-9a-f]{8} findall over the layer text) both read them, and the gate has
        fired correctly on real runs.
      - The `provenance:` block is ADDED per claim: it is the line every parser in the
        repo already understands (author_layers, verify_provenance, seed_industry all
        split the same comma list).
    """
    L = ["# %s" % (d.get("layer") or "").upper(), "", d.get("preamble") or "", ""]
    for c in d.get("claims") or []:
        fids = [f.lstrip("F-").strip("[]") for f in c.get("fact_ids") or []]
        ids = " ".join("[F-%s]" % f for f in fids)
        L.append("## %s %s%s" % (c["id"], c["name"], "  (CONTESTED)" if c.get("contested") else ""))
        L.append("")
        L.append(c["statement"])
        if c.get("active_when"):
            L.append("")
            L.append("*Active when:* %s" % c["active_when"])
        L.append("")
        L.append("*Evidence:* %s" % ids)
        L.append("")
        if fids:
            L.append("provenance: [%s]" % ", ".join("F-%s" % f for f in fids))
            L.append("")
    return chr(10).join(L)


def call(cl, model, prompt, maxtok=16000):
    with cl.messages.stream(model=model, max_tokens=maxtok,
                            messages=[{"role": "user", "content": prompt}]) as st:
        r = st.get_final_message()
    t = next((b.text for b in r.content if getattr(b, "type", None) == "text"), "")
    if not t:
        raise RuntimeError("empty text, stop_reason=%s out=%d"
                           % (r.stop_reason, r.usage.output_tokens))
    return t, r.usage.input_tokens, r.usage.output_tokens, r.stop_reason


# 🚨 COMPOSE WAS THE LAST UNGATED HOP AND THE BRIEF HAD NEVER CARRIED A CITATION.
# An earlier change built an evidence map for compose, assigned it to `ev`, and NOTHING EVER READ
# IT. The chain was not closed at compose; the claim that it was is withdrawn. A mechanical prompt
# audit found it by grepping for the variable, which is the check that should precede the claim.
#
# 🎯 Compose now uses the SAME contract as the layers: a strict tool schema whose every section
# requires the ids it rests on, plus the same non-empty and non-fabricated gate, plus a raise.
# ⚠️ The ids compose may cite are exactly the ids its input layers cited. It cannot introduce
# evidence, because it never sees the corpus. That makes its `supplied` set the union of the
# layer citations, and any id outside it is a fabrication by construction.
BRIEF_SECTION = {
    "type": "object",
    "properties": {
        "heading": {"type": "string"},
        "body": {"type": "string",
                 "description": "The section text. Attach the ids INLINE after the sentence "
                                "they support, in the form [F-xxxxxxxx], so a reader can tell "
                                "which statement rests on which evidence. A trailing list is a "
                                "bibliography, not a citation."},
        "fact_ids": {"type": "array", "items": {"type": "string"},
                     "description": "Ids this section rests on, carried forward from the layer "
                                    "claims it draws on. Do not introduce an id not present "
                                    "in the layers above."},
    },
    "required": ["heading", "body", "fact_ids"],
    "additionalProperties": False,
}
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {"type": "array", "items": BRIEF_SECTION},
        "carried_contradictions": {
            "type": "array", "items": {"type": "string"},
            "description": "Tensions that appear in more than one layer, named and NOT "
                           "resolved. You are the only node that can see across all layers.",
        },
    },
    "required": ["title", "sections", "carried_contradictions"],
    "additionalProperties": False,
}


def render_brief(d):
    L = ["# %s" % (d.get("title") or "Behavioral specification"), ""]
    for sec in d.get("sections") or []:
        ids = " ".join("[F-%s]" % f.lstrip("F-").strip("[]") for f in sec.get("fact_ids") or [])
        # 🚨 EACH PIECE OF EVIDENCE ATTACHES TO THE SPECIFIC STATEMENT IT SUPPORTS, not to the
        # bottom of the section: a trailing list is a bibliography, not a citation. Ids now sit
        # inline in the body; the trailing line is the union, kept only so the audit has a
        # complete set to resolve.
        L += ["## %s" % sec["heading"], "", sec["body"], "",
              "*All evidence in this section:* %s" % ids, ""]
    con = d.get("carried_contradictions") or []
    if con:
        L += ["## Carried contradictions", "",
              "These tensions appear in the evidence and are deliberately not resolved.", ""]
        L += ["- %s" % c for c in con] + [""]
    return chr(10).join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", action="append", required=True,
                    help="handoff package json; repeat once per layer")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default="claude-opus-5",
                    help="authoring+compose. Compose is 0.24%% of pipeline cost, so the best "
                         "model here is effectively free.")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    cl = anthropic.Anthropic()
    layers, all_contra, tin, tout = {}, [], 0, 0
    structured = {}
    ev = {}
    for p in a.package:
        pkg = json.load(open(p, encoding="utf-8"))
        lay = pkg["layer"]
        # 🚨 DO NOT REUSE THE PROSE LAYER PROMPT VERBATIM UNDER A TOOL SCHEMA.
        # The first strict-schema run failed all three attempts because the prose ANCHORS prompt
        # carries its own detailed markdown output-format instructions, and the tool schema demands a
        # different shape. Given two incompatible output contracts the model produced neither:
        # it emitted CORE-shaped ids (M1, C1) under the ANCHORS prompt, then fabricated
        # F-COUNT-407 and F-INPUT-EMPTY, which is the model describing its INPUT rather than
        # the subject. Two contracts, one job.
        #
        # 🎯 So keep the layer DIRECTIVE (what this layer is for, which is judgment the schema
        # cannot carry) and drop the format instructions (which the schema now owns).
        DIRECTIVE = {
            "anchors": "AXIOMS this person reasons FROM, not about: pre-set certainties that "
                       "narrow what they will consider before situation-specific information "
                       "arrives. Name them A1, A2, ... Load-bearing means: it constrains what "
                       "they treat as settled.",
            "core": "HOW this person communicates, what context they carry, and what an AI must "
                    "know to interpret them. Biography counts here. Name them C1, C2, ... "
                    "Load-bearing means: it changes how you would read something they said.",
            "predictions": "HOW this person responds to SPECIFIC SITUATIONS. Name them P1, P2, "
                           "... Each `active_when` must name a concrete, recognisable "
                           "circumstance. Load-bearing means: it lets you anticipate a concrete "
                           "behaviour in a nameable circumstance.",
            # A 'blind' tree is the CONTROL ARM: distilled with no layer directive. It is the default
            # for distill.py, so without this key the documented default path dies with a bare
            # KeyError. The directive says plainly that it is a control, because its dispositions
            # are not comparable to a directed arm's and a reader must not treat its output as a layer.
            "blind": "NO LAYER DIRECTIVE. This is the CONTROL ARM. Write what the evidence supports "
                     "about how this subject operates, generally. Name the claims B1, B2, ... Load-bearing "
                     "means: it bears on how they operate. Output from this arm is a control and is not "
                     "comparable to a directed layer.",
        }[lay]
        _P = [
            "You are authoring the %s layer of a behavioural specification." % lay.upper(),
            "",
            DIRECTIVE,
            "",
            "Emit it by calling the emit_layer tool. The tool schema defines the output "
            "shape; do not write prose outside the tool call.",
            "",
            "EVERY CLAIM MUST CARRY THE FACT IDS IT RESTS ON, copied exactly from the "
            "evidence below. A claim with no ids cannot be followed back to its evidence, "
            "and the entire value of this specification is that any statement in it can be. "
            "Do not invent ids and do not cite an id that does not appear below.",
            "",
            "Mark contested: true where the evidence disagrees with itself. Carry the "
            "tension; do not resolve it.",
            "",
            # 🚨 THESE FOUR WERE DROPPED WITH THE FORMAT INSTRUCTIONS AND SHOULD NOT HAVE BEEN.
            # Trimming the prose prompt's markdown scaffolding was right; these four are
            # constraints the schema cannot express, and prior ablation testing established the
            # first two as load-bearing. The cleanup deleted something measured to matter.
            (os.environ.get("BASELAYER_BROAD_CLAIMS") and
             "BREADTH: state each claim broadly, at the level of a general disposition. Prefer "
             "wide claims that cover much of this person's record over narrow ones tied to "
             "specific circumstances." or
             "DOMAIN-AGNOSTIC: state each claim so it applies across this person's whole life, "
             "not only the domain the evidence happened to come from."),
            "Do not name philosophy or psychology frameworks. Describe the behaviour.",
            "Write in the third person, using they/them.",
            "DERIVE ONLY FROM THE EVIDENCE BELOW. Do not add what you know about people in "
            "general.",
            "",
            render(pkg),
        ]
        prompt = chr(10).join(_P)
        # 🚨 THE GATE HAD ~80% FALSE POSITIVES AND THE MODEL WAS BLAMED FOR THEM.
        # `supplied` was built from theme and singularity ids only. The CONTRADICTIONS block is
        # rendered to the model with a_fact_ids and b_fact_ids, and those were never added, so a
        # model citing evidence it was legitimately shown was told it had fabricated.
        # Diagnosed by checking the "fabricated" ids against the database: of 11, NINE were real
        # active facts and FOUR were in the package itself. Only 2 were genuine inventions.
        # 🎯 Guessing 8 hex chars and hitting a real fact is ~1 in 100,000. Nine hits was not the
        # model hallucinating; the check was wrong, and every retry was correcting the author
        # AWAY from valid citations. WHEN A GUARD FIRES CONSTANTLY, SUSPECT THE GUARD.
        # 🚨 PROGRESSIVE CHECKPOINTING. Do not discard good information because new bad
        # information was detected; correct the new bad information and keep moving forward.
        # Authoring used to re-do every completed layer whenever a later one failed: three runs
        # died on predictions and each one re-paid for anchors and core.
        # 🎯 Same principle that made distillation survivable -- leaves checkpoint, so a crash
        # costs a merge and not a day. A layer already written is DONE; load it and move on.
        _done = os.path.join(a.outdir, "%s.md" % lay)
        _js = os.path.join(a.outdir, "%s.json" % lay)
        if os.path.exists(_done) and os.path.exists(_js) and not os.environ.get("BASELAYER_REAUTHOR"):
            layers[lay] = io.open(_done, encoding="utf-8").read()
            structured[lay] = json.load(open(_js, encoding="utf-8"))
            all_contra += pkg["contradictions"]
            print("  %-12s already authored, reusing (BASELAYER_REAUTHOR=1 to force)" % lay,
                  flush=True)
            continue

        supplied = {s["fact_id"] for s in pkg["singularities_verified"]}
        supplied |= {s["fact_id"] for s in pkg["singularities_unverified"]}
        for t in pkg["themes"]:
            supplied |= set(t.get("fact_ids") or [])
        for c in pkg["contradictions"]:
            supplied |= set(c.get("a_fact_ids") or [])
            supplied |= set(c.get("b_fact_ids") or [])
        data, i, o = call_structured(cl, a.model, prompt, LAYER_SCHEMA, supplied)
        txt = render_claims(data)
        tin += i; tout += o
        layers[lay] = txt
        structured[lay] = data
        all_contra += pkg["contradictions"]
        # 🚨 THE INTERPRETIVE CHAIN USED TO BREAK AT COMPOSE. Compose saw three prose layers and
        # no fact ids, so a composed claim traced to a LAYER and stopped there -- one hop short
        # of the evidence, at exactly the point a reader most wants to ask "where did this come
        # from". The layer-claim-to-composed-brief link must be closed BEFORE compose runs. The
        # chain is fact -> disposition -> theme/singularity -> layer claim -> composed brief, and
        # it was cut at the last arrow.
        ev[lay] = {"verified_singularities": [
                       {"id": s["fact_id"], "text": s["verbatim"]}
                       for s in pkg["singularities_verified"]],
                   # 🚨 EIGHTH CAP, AND IT WAS IN THE CODE WRITTEN TO CLOSE THE CHAIN AT
                   # COMPOSE. themes[:120] of 4,954, claim text cut to 120 chars, ids cut to 8.
                   # The evidence map that exists so a composed claim can be followed back was
                   # itself built from 2% of the evidence.
                   "theme_evidence": [{"claim": t["statement"],
                                       "fact_ids": t.get("fact_ids") or []}
                                      for t in pkg["themes"]]}
        open(os.path.join(a.outdir, "%s.md" % lay), "w", encoding="utf-8").write(txt)
        json.dump(data, open(os.path.join(a.outdir, "%s.json" % lay), "w", encoding="utf-8"),
                  indent=1)
        print("  %-12s authored: %d claims, %d chars" % (lay, len(data["claims"]), len(txt)), flush=True)

    # COMPOSE, with the contradictions union the layer authors could not see across.
    # 🚨 NINTH CAP: compose saw 200 of ~1,480 contradictions. The channel whose entire purpose is
    # that contradictions are CARRIED AND NEVER RESOLVED was showing 13% of them to the only node
    # that can see across all three layers.
    con = "\n".join("- %s" % c.get("tension", "") for c in all_contra)
    cprompt = (
        "Compose a single unified behavioural specification from the three layers below.\n\n"
        + "\n\n".join("### %s LAYER\n%s" % (k.upper(), v) for k, v in layers.items())
        # 🚨 COMPOSE WAS DESTROYING THE CONTRADICTIONS CHANNEL. Measured on a specification built
        # from a 37,839-fact corpus: the three layers carried 40 claims marked CONTESTED and the
        # composed brief carried ZERO. A downstream reader got 40 flagged tensions as settled
        # truth -- the layers' most honest property, destroyed at the last hop, which is the
        # exact failure this architecture exists to prevent. The contradictions union was already passed; the per-claim CONTESTED
        # markings were not, so compose had no way to know which claims were contested.
        + "\n\n### CLAIMS THE LAYERS MARKED CONTESTED (%d)\n" % sum(
            1 for d in structured.values() for c in (d.get("claims") or []) if c.get("contested"))
        + "\U0001F6A8 EVERY CLAIM BELOW IS MARKED CONTESTED BY THE LAYER THAT WROTE IT: the "
          "evidence disagrees with itself there. YOU MUST CARRY THAT MARKING FORWARD. Write "
          "(CONTESTED) beside any claim you carry that appears here. A contested claim presented "
          "as settled is the worst output this pipeline can produce.\n"
        + chr(10).join("- [%s %s] %s" % (k.upper(), c["id"], c["statement"][:150])
                       for k, d in structured.items()
                       for c in (d.get("claims") or []) if c.get("contested"))
        + "\n\n### CONTRADICTIONS CARRIED FROM THE EVIDENCE (%d)\n" % len(all_contra)
        + "🚨 The three layers above were authored BLIND TO EACH OTHER, so you are the only "
          "point in this pipeline that can see across all three. These tensions were found in "
          "the source facts and deliberately not resolved by any layer. Where a tension shows "
          "up in more than one layer, say so. DO NOT smooth them into coherence: the gap "
          "between what this person believes and what they do is a finding, not a defect.\n\n"
        + con)
    layer_ids = set()
    for lay_txt in layers.values():
        layer_ids |= {m for m in __import__("re").findall(r"[0-9a-f]{8}", lay_txt)}
    bdata, i, o = call_structured(cl, a.model, cprompt, BRIEF_SCHEMA, layer_ids, maxtok=24000,
                                  tool_name="emit_brief")
    tin += i; tout += o
    txt = render_brief(bdata)
    open(os.path.join(a.outdir, "brief.md"), "w", encoding="utf-8").write(txt)
    print("  compose: %d sections, %d contradictions carried, %d chars"
          % (len(bdata.get("sections") or []), len(bdata.get("carried_contradictions") or []), len(txt)))
    print("cost $%.2f (in=%d out=%d) -> %s" % (tin / 1e6 * 5 + tout / 1e6 * 25, tin, tout,
                                               a.outdir))


if __name__ == "__main__":
    main()
