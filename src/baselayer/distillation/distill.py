"""INTERPRETIVE DISTILLATION. Exhaustive, auditable, hierarchical summarisation.

EXPERIMENTAL. Tested only via 10 mutation tests over validate()/audit_citations();
see baselayer/distillation/__init__.py for the full status.

EVERY FACT PASSES THROUGH BY CONSTRUCTION. There is no stopping rule and no coverage
estimate: you do not stop, you finish. Coverage is a property of the control flow.

Design decisions and why, so a later reader does not re-litigate them:

- FOUR-CHANNEL LEAF SCHEMA with a RESERVED SINGULARITIES LANE. A tree is a frequency
  amplifier: a recurrent theme enters every merge with many tickets, a singular fact must
  win log(N) elimination rounds. "Significance is not frequency" is not merely unenforced
  by a plain summariser, it is INVERTED. So singularities are carried VERBATIM with their
  ids and are ineligible for paraphrase or merging. A prompt instruction against a
  structural bias loses; the schema has to make the drop impossible, not discouraged.

- THE SINGULARITY LANE ALSO RECONSTITUTES THE MISSING JUDGE. The deepest objection to a
  tree is that no node ever holds both a global view and primary evidence: leaves have
  evidence and no view, the root has view and only paraphrase. Carrying singularities
  verbatim to the root means the root holds both, for exactly the facts where singularity
  is the point.

- PER-FACT DISPOSITION AT THE LEAF. "Every fact was presented to a model" is not "the model
  considered every fact". Discovery's "I looked" requires a recorded decision per item.
  Without a disposition the honest description is "everything was streamed past a lossy
  channel".

- CONTRADICTIONS ARE CARRIED, NEVER RESOLVED. Summarisation is a consensus operator; handed
  "believes X" and "acts not-X" it harmonises. The declared-versus-operative gap is the
  thing this project most needs to carry and the thing a tree is built to erase.

- LEVEL 1 IS ORDER-INDEPENDENT. Each leaf is a pure function of its own chunk. Order can
  only enter at level 2 and above, which collapses the order space from 76! to a handful
  and makes order sensitivity measurable instead of astronomical.
"""
import os, sys, json, re, sqlite3, time, argparse
from collections import Counter

# This module now lives inside the baselayer package and imports nothing from it, so the
# old walk-up-to-the-checkout shim is gone (from here, it resolved to a path that does not
# exist). BASELAYER_SRC is still honoured so a caller can pin which checkout resolves first.
_src = os.environ.get("BASELAYER_SRC")
if _src:
    sys.path.insert(0, _src)
import anthropic

LEAF_SCHEMA = """Return ONLY a JSON object, no prose outside it:
{
 "themes":[{"statement":"...","fact_ids":["id","id"]}],
 "singularities":[{"fact_id":"id","verbatim":"exact fact text, unchanged","why":"one clause"}],
 "contradictions":[{"a_fact_ids":["id"],"b_fact_ids":["id"],"tension":"..."}],
 "dispositions":{"<fact_id>":"theme|singular|not_load_bearing"}
}"""

# 🚨 `not_load_bearing` IS MEANINGLESS WITHOUT A DIRECTIVE, AND THE FIRST RUNS SHIPPED WITHOUT
# ONE. Haiku dismissed 102 of 407 facts as not load-bearing and Sonnet dismissed 5. Neither was
# told load-bearing FOR WHAT. The model was asked to make a judgment whose criterion was never
# stated, so it supplied its own, and the 20x disagreement between two models is what an
# unstated criterion looks like when you measure it.
#
# Fact coverage must be 100% FOR EACH LAYER, so the pass is PER LAYER, not shared. A fact that
# is noise for ANCHORS is often the substance of CORE: measured on a 407-fact corpus, an ANCHORS
# author read 0 of 103 experienced/biography facts while a CORE author read 30 of the same facts
# as its FIRST action. A directive-blind tree summarises toward neither.
#
# ✅ THESE WORDINGS ARE SETTLED, not an undecided constant. The first half of each states what
# the layer is for; the "Load-bearing means" clause is the operative part. They are recorded
# explicitly rather than left implicit because they demonstrably move the output: directed arms
# dismiss ~98 of 407 facts where the blind control dismisses 65, so changing the wording changes
# what gets discarded from the corpus.
#
# ⚠️ KNOWN LIMITS OF THE CURRENT WORDING, carried deliberately, not oversights:
#   - ANCHORS "constrains what they treat as settled" privileges conviction over disposition.
#   - CORE "changes how you would read something they said" is a READER's criterion, so it
#     smuggles an audience into a property of the person.
#   - PREDICTIONS "a nameable circumstance" is the strictest of the three and will discard
#     situational-but-diffuse material.
#   - All three assume `not_load_bearing` means DISCARDABLE. It could instead mean "carried
#     but unweighted", which would preserve the fact while marking it. Open by choice.
LAYER_DIRECTIVES = {
    "anchors": ("AXIOMS this person reasons FROM, not about: pre-set certainties that narrow "
                "what they will consider before situation-specific information arrives. "
                "Load-bearing means: it constrains what they treat as settled."),
    "core": ("HOW this person communicates, what context they carry, and what an AI must know "
             "to interpret them. Biography counts here. Load-bearing means: it changes how you "
             "would read something they said."),
    "predictions": ("HOW this person responds to SPECIFIC SITUATIONS. Load-bearing means: it "
                    "lets you anticipate a concrete behaviour in a nameable circumstance."),
    "blind": ("No layer directive. Load-bearing means: it bears on how this person operates, "
              "generally. THIS ARM IS THE CONTROL and its dispositions are not comparable to a "
              "directed arm's."),
}

LEAF_PROMPT = """You are one node in an auditable distillation of a person's fact base. You have been given a COMPLETE chunk. Nothing was selected for you and nothing is hidden.

THE LAYER YOU ARE SERVING: %s

Every judgment below is made RELATIVE TO THAT LAYER. A fact that is noise for one layer is the substance of another.

Your output is not a summary for a reader. It is an intermediate that a later node will read INSTEAD OF these facts, so anything you drop is gone for good.

Four channels, and they do not compete for space:

THEMES: what recurs. Synthesise. Cite the ids you drew on.

SINGULARITIES: facts that no theme statement covers, and that would change how someone models this person if known. Carry the fact text VERBATIM and unchanged. A fact can be decisive and appear exactly once; frequency is not significance. Undramatic facts qualify: a quiet procedural habit that governs how decisions get made matters more than a vivid one-off. Do not paraphrase these and do not merge them.

CONTRADICTIONS: where the chunk disagrees with itself, especially stated belief against reported action. DO NOT RESOLVE THESE. Carry the tension with both sides' ids. A contradiction is a finding, not a defect to smooth.

DISPOSITIONS: every fact id in the chunk gets exactly one verdict. theme (folded into a theme), singular (carried in the singularity lane), or not_load_bearing (read and judged not to bear on how this person operates). Omitting an id is not an option.

CHUNK: %s
%d facts.

%s

%s"""

NODE_PROMPT = """You are an interior node in an auditable distillation.

THE LAYER YOU ARE SERVING: %s
 Your inputs are the outputs of nodes beneath you, NOT raw facts. You cannot see the underlying text except where a singularity was carried verbatim.

Merge the themes. Carry EVERY singularity upward unchanged unless another singularity says the same thing, in which case keep one and cite both ids. Carry every contradiction; do not resolve any.

You are the wider view. Singularities reached you verbatim precisely so that you can judge them with a view their own chunk did not have.

INPUTS:
%s

%s"""


# Rates per MTok. Never price from memory: these are the published first-party rates and a
# wrong one silently misreports the budget question this study exists to answer.
_RATES = {"claude-opus-5": (5, 25), "claude-sonnet-5": (3, 15), "claude-haiku-4-5": (1, 5)}


def _cost(model, tin, tout):
    # RAISE on an unknown id. The comment above _RATES says a wrong rate "silently misreports
    # the budget question this study exists to answer" -- and a .get() default did exactly
    # that, pricing any future model at Sonnet rates. Default-deny is the right shape here:
    # refuse to price a model whose rate was never published rather than invent one.
    if model not in _RATES:
        raise KeyError("no published rate for %r; add it to _RATES rather than defaulting, "
                       "or the cost figure is fiction" % model)
    i, o = _RATES[model]
    return tin / 1e6 * i + tout / 1e6 * o


def call(cl, model, prompt, maxtok=16000):
    """Always stream. The SDK refuses non-streaming requests that could exceed 10 minutes, and
    a four-channel node with a per-fact disposition block is exactly that shape once max_tokens
    is large enough to stop truncating. Raising the ceiling without switching to streaming is
    what killed the first repaired run.

    Leaf ceiling is 16000 rather than 8000 because 5 of 7 Sonnet leaves parse-failed at 8000:
    60 dispositions plus themes plus verbatim singularities does not fit, and a truncated node
    is an empty node, which the audit then reports as content that was dropped.
    """
    # 🚨 NO RETRY KILLED A 631-CHUNK RUN AT CHUNK 380. `overloaded_error` is transient and
    # expected on a long job; treating it as fatal discarded 380 chunks of completed work.
    # A run whose length is the whole point cannot be one 503 away from nothing.
    import time as _t
    last = None
    for attempt in range(6):
        try:
            with cl.messages.stream(model=model, max_tokens=maxtok,
                                    messages=[{"role": "user", "content": prompt}]) as st:
                r = st.get_final_message()
            break
        except Exception as e:
            msg = str(e).lower()
            transient = ("overload" in msg or "rate" in msg or "429" in msg
                         or "529" in msg or "timeout" in msg or "connection" in msg)
            if not transient or attempt == 5:
                raise
            last = e
            wait = min(60, 2 ** attempt * 3)
            print("    transient API error (%s), retry %d/5 in %ds"
                  % (type(e).__name__, attempt + 1, wait), flush=True)
            _t.sleep(wait)
    t = next((b.text for b in r.content if getattr(b, "type", None) == "text"), "")
    return t, r.usage.input_tokens, r.usage.output_tokens, r.stop_reason


def call_json(cl, model, prompt, maxtok, label, stats):
    """Call, parse, and RETRY once on failure. Never silently return an empty node.

    An early run of this script reported "singularities L1=55 -> L2=0, survival 0%". That reads
    as the frequency amplifier destroying the reserved lane. It was not. The L2 node returned
    unparseable text, `parse(txt) or {}` swallowed it, and the audit counted parse failures AT
    LEAVES ONLY, so an instrument failure was rendered as a finding about the architecture.
    That is the defect class to watch for throughout this pipeline: a step that reports a
    result when it failed to run.

    So: parse failures are counted at EVERY level, truncation is detected from stop_reason
    rather than inferred, and a failed node is retried with the broken text in hand before
    anything downstream is allowed to treat it as empty.
    """
    txt, i, o, stop = call(cl, model, prompt, maxtok)
    stats["in"] += i
    stats["out"] += o
    d = parse(txt)
    if d is None:
        stats["parse_fail"].append(label)
        if stop == "max_tokens":
            stats["truncated"].append(label)
        rep = (prompt + "\n\nYour previous reply was not valid JSON"
               + (" and was CUT OFF by the output limit, so emit FEWER themes but keep every "
                  "singularity and contradiction." if stop == "max_tokens" else ".")
               + " Return ONLY the JSON object, complete and closed.")
        txt, i, o, stop = call(cl, model, rep, maxtok)
        stats["in"] += i
        stats["out"] += o
        d = parse(txt)
        if d is None:
            stats["parse_fail_final"].append(label)
            open("%s.RAWFAIL.txt" % label.replace("/", "_"), "w", encoding="utf-8").write(txt)
            return None, stop
        stats["repaired"].append(label)
    if stop == "max_tokens" and label not in stats["truncated"]:
        stats["truncated"].append(label)
    # SCHEMA ENFORCEMENT. One retry naming the exact violations, then record and move on
    # rather than storing a node nobody validated.
    bad = validate(d, stats.get("_expect_ids"))
    if bad:
        stats["schema_fail"].append((label, bad))
        rep = (prompt + "\n\nYour previous reply violated the schema: " + "; ".join(bad)
               + ". Allowed disposition values are exactly: " + ", ".join(DISPOSITIONS)
               + ". Every fact id in the chunk needs one. Return ONLY the corrected JSON.")
        txt2, i2, o2, stop2 = call(cl, model, rep, maxtok)
        stats["in"] += i2
        stats["out"] += o2
        d2 = parse(txt2)
        if d2 is not None and not validate(d2, stats.get("_expect_ids")):
            stats["schema_repaired"].append(label)
            return d2, stop2
        stats["schema_fail_final"].append(label)
    return d, stop


DISPOSITIONS = ("theme", "singular", "not_load_bearing")


def validate(d, ids=None):
    """Return a list of schema violations. Empty list means the node is well-formed.

    🚨 THE SCHEMA WAS ADVISORY AND SOMETHING WALKED THROUGH IT. The predictions run emitted a
    FOURTH disposition value, `contradiction`, on 3 facts. It was never specified, nothing
    rejected it, and it was stored. This is the unenforced-container problem in general: a
    schema file elsewhere in this project specified an output container exactly while nothing
    ever read it, and four separator variants shipped across five runs as a result.

    A container that cannot reject anything is documentation, not a schema. This one rejects.
    """
    bad = []
    if not isinstance(d, dict):
        return ["not an object"]

    # 🚨 FABRICATED IDS. Found by auditing the ARTIFACT against the DATABASE, the only check that
    # could have seen it. Three ids in the handoff packages resolved to no fact at all, not even
    # a superseded one: two appeared as THEME ids in all three layers and one as a SINGULARITY
    # id. They were invented AT A LEAF and rode every tier to the root.
    #
    # 🎯 EVERY EXISTING CHECK WAS BLIND TO THIS BY CONSTRUCTION. The invented-above-the-leaf test
    # compares each tier against the leaves, so an id invented AT a leaf is baseline-correct. The
    # authoring gate compared against the package, and the package inherited the fabrication.
    #
    # ⚠️ AND THE CHECK IS FREE: this node was handed exactly these ids, so anything outside that
    # set is fabricated, decidable at emission with no database call. The missing check was the
    # cheapest one in the pipeline.
    # 🚨 DETECTION IS NOT REMOVAL, AND FLAGGING ALONE SHIPPED THE FABRICATION ANYWAY.
    # Making this a schema violation triggered the retry, but a node that still fabricates after
    # its retries is stored with `schema_fail_final` and the bad ids intact. Re-distilling a
    # 407-fact corpus with the check live caught 2 fabrications per layer AND still left 2-3
    # unresolvable ids in every tree. An audit that records a defect and then passes it
    # downstream is the most common instrument failure in this codebase.
    #
    # 🎯 SO STRIP. A theme keeps only the ids it was actually given; a singularity whose id was
    # never in the chunk is DROPPED WHOLE, because its verbatim text cannot be trusted to belong
    # to this person if the id it claims does not exist.
    # ⚠️ The violation is still reported, so the RATE stays visible. Stripping fixes the artifact;
    # it must not hide the measurement.
    # 🚨 ORDER IS LOAD-BEARING: DETECT FIRST, THEN STRIP. These two blocks ran the other way round
    # for a long stretch after the strip was added, which made BOTH violation branches
    # unreachable: the detector was handed data the stripper had already cleaned. The comment above
    # said the rate stays visible. It did not. Three of four ledger metrics were pinned at 100% as
    # a result, and the shipped ledger shows citations_clean_pct discriminating at 98.7-99.4 BEFORE
    # the strip and reading exactly 100.0 after it. A working measurement became a tautology and
    # the improvement read as progress. `test_metrics_can_fail.py` now plants each of these
    # defects and asserts the metric notices.
    if ids is not None:
        ok = set(ids)
        for t in (d.get("themes") or []):
            if isinstance(t, dict):
                out = [f for f in (t.get("fact_ids") or []) if f not in ok]
                if out:
                    bad.append("theme cites ids not in this chunk: %s" % ", ".join(sorted(out)[:5]))
        for sg in (d.get("singularities") or []):
            if isinstance(sg, dict) and sg.get("fact_id") and sg["fact_id"] not in ok:
                bad.append("singularity id not in this chunk: %s" % sg["fact_id"])
        # DISPOSITIONS WERE NEVER SCOPE-CHECKED AT ALL. They are merged across leaves with
        # dict.update(), which is last-writer-wins, so a verdict for a foreign id OVERWRITES the
        # real verdict from the leaf that actually read that fact. Live, not theoretical: a
        # shipped ledger row records 408 dispositions on a 407-fact corpus.
        _disp = d.get("dispositions")
        if isinstance(_disp, dict):
            foreign = sorted(k for k in _disp if k not in ok)
            if foreign:
                bad.append("dispositions for ids not in this chunk: %s"
                           % ", ".join(foreign[:5]))

    # PERSIST WHAT WE ARE ABOUT TO REMOVE. Everything above detects into `bad`, and then the
    # stripper below empties the population the audit block later recounts. That is how three
    # ledger metrics became tautologies: the detector ran, the stripper cleaned, and the audit
    # measured the cleaned data and reported 100%. Counting here -- BEFORE the strip, on the
    # object that gets stored -- is what makes the rate survive to the ledger.
    if ids is not None:
        ok = set(ids)
        _v = {"theme_ids": 0, "singularities": 0, "dispositions": 0}
        for t in (d.get("themes") or []):
            if isinstance(t, dict):
                _v["theme_ids"] += sum(1 for f in (t.get("fact_ids") or []) if f not in ok)
        for sg in (d.get("singularities") or []):
            if isinstance(sg, dict) and sg.get("fact_id") and sg["fact_id"] not in ok:
                _v["singularities"] += 1
        if isinstance(d.get("dispositions"), dict):
            _v["dispositions"] += sum(1 for k in d["dispositions"] if k not in ok)
        _v["total"] = _v["theme_ids"] + _v["singularities"] + _v["dispositions"]
        prev = d.get("_stripped") or {}
        d["_stripped"] = {k: prev.get(k, 0) + v for k, v in _v.items()}

    # NOW STRIP. A theme keeps only the ids it was actually given; a singularity whose id was
    # never in the chunk is DROPPED WHOLE, because its verbatim text cannot be trusted to belong
    # to this person if the id it claims does not exist. A foreign disposition is removed so it
    # cannot overwrite a real one downstream.
    if ids is not None:
        ok = set(ids)
        for t in (d.get("themes") or []):
            if isinstance(t, dict) and t.get("fact_ids"):
                t["fact_ids"] = [f for f in t["fact_ids"] if f in ok]
        keep = []
        for sg in (d.get("singularities") or []):
            if not isinstance(sg, dict) or not sg.get("fact_id") or sg["fact_id"] in ok:
                keep.append(sg)
        d["singularities"] = keep
        if isinstance(d.get("dispositions"), dict):
            d["dispositions"] = {k: v for k, v in d["dispositions"].items() if k in ok}

    for k in ("themes", "singularities", "contradictions"):
        if not isinstance(d.get(k, []), list):
            bad.append("%s is not a list" % k)
    disp = d.get("dispositions")
    # ⚠️ INTERIOR NODES HOLD NO RAW IDS, so demanding a disposition block from them produced a
    # schema retry telling the node "every fact id in the chunk needs one" when there is no
    # chunk -- an instrument artifact landing in schema_fail_final as if the node had failed.
    # `ids` is None for interior nodes and a list for leaves; that is the discriminator.
    if ids is None and disp is None:
        pass
    elif not isinstance(disp, dict):
        bad.append("dispositions is not an object")
    else:
        # 🚨 A VALIDATOR MUST REJECT MALFORMED INPUT, NOT CRASH ON IT. A leaf on a 3,688-fact
        # corpus emitted a disposition whose VALUE was a list rather than a string, and this line
        # raised TypeError: unhashable type: 'list' -- killing the run instead of recording a
        # violation. Same shape as the other instrument failures here: the instrument failed at
        # exactly the point where it was supposed to catch a failure.
        unknown = sorted({v if isinstance(v, str) else "<non-string:%s>" % type(v).__name__
                          for v in disp.values()
                          if not isinstance(v, str) or v not in DISPOSITIONS})
        if unknown:
            bad.append("unknown disposition values %s (allowed: %s)"
                       % (unknown, list(DISPOSITIONS)))
        if ids is not None:
            missing = [i for i in ids if i not in disp]
            if missing:
                bad.append("%d of %d fact ids have no disposition" % (len(missing), len(ids)))
    for s in (d.get("singularities") or []):
        if not isinstance(s, dict) or not s.get("fact_id") or "verbatim" not in s:
            bad.append("singularity missing fact_id or verbatim")
            break
    return bad


def parse(t):
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        try:
            return json.loads(re.sub(r",(\s*[}\]])", r"\1", m.group(0)))
        except Exception:
            return None


def partition(rows, strategy, size, seed=0):
    """Assign facts to EQUAL-SIZED chunks by different criteria.

    CHUNK SIZE IS HELD CONSTANT ACROSS STRATEGIES ON PURPOSE. Predicate groups are wildly
    uneven (5,285 facts against 5 on a 37,839-fact corpus), so a naive by-predicate partition
    varies size and composition together and the comparison cannot attribute a difference to
    either. Every strategy here ORDERS the facts and then cuts equal chunks, so the only
    thing that varies is WHICH FACTS SHARE A CHUNK.

    THE PARTITION IS NOT NEUTRAL AND THIS IS THE POINT OF THE EXPERIMENT. Selection happens
    competitively WITHIN a chunk: two facts that would synthesise into one theme if
    co-present can both die separately if split, and a contradiction can only be seen by a
    node whose chunk holds both sides. Chunking is the hidden selector, the same role the
    fact cap played one level up.

    'random' IS THE NULL ARM and is not optional. If survival under a content-based
    partition does not beat survival under random packing, the partition is doing nothing.

    Note that predicate/category/semantic are all functions of CONTENT and will produce
    correlated partitions, so agreement between them is weaker evidence than it looks.
    'time' is the only genuinely orthogonal axis available.
    """
    import random as _r
    rs = list(rows)
    if strategy == "random":
        _r.Random(seed).shuffle(rs)
    elif strategy == "predicate":
        rs.sort(key=lambda r: ((r[2] or "~"), r[0]))
    elif strategy == "category":
        rs.sort(key=lambda r: ((r[3] or "~"), r[0]))
    elif strategy == "predcat":
        rs.sort(key=lambda r: ((r[2] or "~"), (r[3] or "~"), r[0]))
    elif strategy == "time":
        rs.sort(key=lambda r: (r[4] if len(r) > 4 and r[4] is not None else 0, r[0]))
    elif strategy == "semantic":
        rs = _semantic_order(rs, seed)
    else:
        raise ValueError("unknown partition %r" % strategy)
    out = []
    n = -(-len(rs) // size)
    for i in range(0, len(rs), size):
        part = rs[i:i + size]
        preds = Counter((r[2] or "?") for r in part).most_common(2)
        tag = "+".join("%s(%d)" % (p, c) for p, c in preds)
        out.append(("%s-%d/%d %s" % (strategy, i // size + 1, n, tag), part))
    return out


def _semantic_order(rs, seed):
    """Order by embedding cluster so semantically near facts share a chunk.

    Stem-stripped before embedding: every fact_text carries a `user <predicate>` prefix, and
    leaving it in makes the semantic partition a covert copy of the predicate partition.
    """
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import KMeans
    import numpy as np
    txt = []
    for r in rs:
        p = (r[2] or "").replace("_", " ")
        s = r[1]
        for pre in ("user %s " % p, "%s " % p, "user "):
            if pre.strip() and s.lower().startswith(pre.lower()):
                s = s[len(pre):]
                break
        txt.append(s)
    m = SentenceTransformer("BAAI/bge-small-en-v1.5")
    E = m.encode(txt, normalize_embeddings=True, batch_size=256, show_progress_bar=False)
    k = max(2, min(40, len(rs) // 20))
    lab = KMeans(n_clusters=k, n_init=4, random_state=seed).fit_predict(E)
    return [r for _, r in sorted(zip(lab, rs), key=lambda t: (t[0], t[1][0]))]


def render(d):
    return "CHUNK %s (%s facts)\nTHEMES: %s\nSINGULARITIES: %s\nCONTRADICTIONS: %s" % (
        d.get("_chunk", "?"), d.get("_n", "?"),
        "; ".join("%s %s" % (t.get("statement", ""), t.get("fact_ids", []))
                  for t in (d.get("themes") or [])),
        "; ".join("[%s] %s" % (s.get("fact_id", ""), s.get("verbatim", ""))
                  for s in (d.get("singularities") or [])),
        "; ".join(x.get("tension", "") for x in (d.get("contradictions") or [])))



def audit_citations(leaves):
    """Aggregate the citation audit. THE ONE IMPLEMENTATION, called by main() and by the tests.

    THIS FUNCTION EXISTS BECAUSE THE TESTS PREVIOUSLY RE-IMPLEMENTED IT. A test that copies the
    arithmetic it is checking cannot catch a change to the original: pinning clean_pct in main()
    left every test passing. That is the same defect the suite was written to catch -- exercising
    something adjacent to the number rather than the number -- one level up, and it survived a
    review that was looking for exactly it.

    `clean_pct` is the rate of ATTEMPTED citations that were legitimate, measured from counts
    taken before the stripper ran. `survived_stripper` is a separate INVARIANT and must be 0;
    folding it into the rate is what made the old metric a tautology.
    """
    cited = survived = 0
    for d in leaves:
        own = set(d.get("_ids") or [])
        for t in (d.get("themes") or []):
            for fid in (t.get("fact_ids") or []):
                cited += 1
                if fid not in own:
                    survived += 1
        for sg in (d.get("singularities") or []):
            cited += 1
            if sg.get("fact_id") not in own:
                survived += 1
    stripped = {"theme_ids": 0, "singularities": 0, "dispositions": 0, "total": 0}
    for d in leaves:
        for k, v in (d.get("_stripped") or {}).items():
            stripped[k] = stripped.get(k, 0) + v
    fab = stripped["theme_ids"] + stripped["singularities"]
    attempted = cited + fab
    return {"cited": cited, "fabricated": fab, "attempted": attempted,
            "survived_stripper": survived, "stripped": stripped,
            "clean_pct": 100.0 * cited / max(1, attempted)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-facts", type=int, default=120)
    ap.add_argument("--limit-chunks", type=int, default=0)
    ap.add_argument("--partition", default="predicate",
                    choices=["predicate", "category", "predcat", "random", "semantic", "time"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--layer", default="blind", choices=sorted(LAYER_DIRECTIVES))
    ap.add_argument("--checkpoint", default="", help="write leaves here after every chunk")
    ap.add_argument("--resume-from", default="", help="reload leaves from a checkpoint file")
    ap.add_argument("--write-provenance", action="store_true",
                    help="persist root citations to layer_claim_provenance so a claim-tracing query "
                         "can reach them. WRITES to the corpus db; off by default.")
    a = ap.parse_args()

    c = sqlite3.connect("file:%s?mode=ro" % a.db, uri=True)
    cols = {r[1] for r in c.execute("PRAGMA table_info(memory_facts)")}
    # 🚨 THE `time` ARM USED TO LIE IN ITS OWN RECORD. Both else-branches were "id", so on a
    # corpus without `created_at` the arm the docstring calls "the only genuinely orthogonal
    # axis" sorted by UUID while the stamp and ledger still said partition=time. Whole corpus
    # families are in exactly that state. Worse, where `created_at` does exist it is often the
    # EXTRACTION timestamp, spanning a couple of hours rather than the evidence period -- so
    # even a populated column is not necessarily chronology. Check before trusting this arm.
    tcol = "created_at" if "created_at" in cols else "id"
    if a.partition == "time" and "created_at" not in cols:
        raise SystemExit(
            "--partition time requested but this corpus has no `created_at` column. Sorting "
            "by id would produce UUID order while the stamp recorded 'time', which is an arm "
            "label that lies. Use a different partition, or add real evidence dates.")
    rows = c.execute("SELECT id, fact_text, predicate, category, %s FROM memory_facts "
                     "WHERE superseded_by IS NULL ORDER BY id" % tcol).fetchall()
    # 🚨 8-CHAR IDS ARE 32 BITS AND THE CLAIM IS "NO ITEM DROPPABLE".
    # Fact ids are uuid4; `[:8]` is 32 bits, so collisions are ~0.002% at 407 facts but
    # ~15% at 37,839 -- the corpus this tool exists for. On a collision the prompt shows two
    # facts under one id, `txtof` keeps one text, one disposition overwrites the other, and
    # validation PASSES because the id is present once. A fact vanishes from the "I looked"
    # ledger with no error anywhere. Research code truncates ids routinely; research code whose
    # central claim is a recorded decision per item cannot.
    prefixes = [r[0][:8] for r in rows]
    if len(set(prefixes)) != len(prefixes):
        from collections import Counter as _C
        dupes = [k for k, v in _C(prefixes).items() if v > 1]
        raise SystemExit(
            "ID PREFIX COLLISION: %d of %d 8-char prefixes are not unique (%s ...). Every "
            "guarantee in this tool is per-fact-id, so a collision silently merges two facts "
            "in the prompt, the disposition ledger and the verbatim check at once. Widen the "
            "prefix before running." % (len(prefixes) - len(set(prefixes)), len(prefixes),
                                        ", ".join(dupes[:3])))

    chunks = partition(rows, a.partition, a.max_facts, a.seed)
    if a.limit_chunks:
        chunks = chunks[:a.limit_chunks]
    print("facts=%d  chunks=%d  partition=%s  size=%d  seed=%d"
          % (len(rows), len(chunks), a.partition, a.max_facts, a.seed), flush=True)

    cl = anthropic.Anthropic()
    done = 0
    if a.resume_from and os.path.exists(a.resume_from):
        ck = json.load(open(a.resume_from, encoding="utf-8"))
        done = len(ck.get("leaves") or [])
        print("RESUMING: %d leaves already complete, %d remaining"
              % (done, len(chunks) - done), flush=True)
    stats = {"in": 0, "out": 0, "parse_fail": [], "parse_fail_final": [],
             "repaired": [], "truncated": [], "schema_fail": [], "schema_repaired": [],
             "schema_fail_final": [], "_expect_ids": None}
    leaves = (json.load(open(a.resume_from, encoding="utf-8"))["leaves"]
              if (a.resume_from and os.path.exists(a.resume_from)) else [])
    t0 = time.time()
    for n, (label, fs) in enumerate(chunks, 1):
        if n <= done:
            continue
        body = "\n".join("[%s] %s" % (r[0][:8], r[1]) for r in fs)
        p = LEAF_PROMPT % (LAYER_DIRECTIVES[a.layer], label, len(fs), body, LEAF_SCHEMA)
        stats["_expect_ids"] = [r[0][:8] for r in fs]   # leaf must disposition every id
        d, stop = call_json(cl, a.model, p, 16000, "L1-%02d" % n, stats)
        stats["_expect_ids"] = None                     # interior nodes hold no raw ids
        if d is None:
            d = {"themes": [], "singularities": [], "contradictions": [],
                 "dispositions": {}, "_parse_failed": True}
        d["_chunk"] = label
        d["_n"] = len(fs)
        d["_ids"] = [r[0][:8] for r in fs]
        leaves.append(d)
        # CHECKPOINT. 631 chunks is hours of work; without this a transient failure at 380
        # throws away 380. Written after every leaf, resumed on restart by --resume-from.
        if a.checkpoint:
            json.dump({"leaves": leaves, "stats": {k: v for k, v in stats.items()
                                                   if not k.startswith("_")}},
                      open(a.checkpoint, "w", encoding="utf-8"))
        print("  L1 %2d/%-2d %-30s n=%-4d themes=%-2d SING=%-2d contra=%-2d disp=%d/%d%s"
              % (n, len(chunks), label[:30], len(fs), len(d.get("themes") or []),
                 len(d.get("singularities") or []), len(d.get("contradictions") or []),
                 len(d.get("dispositions") or {}), len(fs),
                 "  PARSE_FAILED" if d.get("_parse_failed") else ""), flush=True)

    # 🚨 THE TREE HAD EXACTLY THREE HARDCODED LEVELS AND DID NOT SCALE.
    #
    # 631 leaves collapse to 79 level-2 nodes, and the old code fed ALL 79 into ONE root call:
    # 395,002 tokens against Haiku's 200,000 limit, a hard 400. It worked on a 407-fact corpus
    # because 7 leaves make 1 interior node and the root saw one input. The failure is invisible below
    # ~64 leaves and certain above ~150, which is every corpus this architecture exists for.
    #
    # A tree that cannot add a level is not a tree, it is three nested loops. Merge now
    # RECURSES: each tier groups by FAN, and the loop continues until one node remains, with a
    # hard stop so a pathological fan cannot spin forever. Every tier is retained -- the trace
    # is the deliverable, so an intermediate tier is evidence, not scratch.
    # 🚨 FAN 8 EMPTIED THE ROOT AT 62 LEAVES. 62 -> 8 -> 1 means the root merges eight nodes
    # carrying 259 themes in ONE call, and it produced zero. The guard below now catches that,
    # but the cause is the fan: a wider fan means fewer tiers and a larger final merge, which is
    # exactly the wrong trade at scale.
    # 🎯 FAN 4 adds a tier and shrinks every merge: 62 -> 16 -> 4 -> 1. Cost rises modestly
    # (more nodes, each cheaper) and each node's input stays within what one call can carry.
    # ⚠️ This changes prompt_hash-adjacent tree shape, so trees before and after are not
    # shape-comparable. It does not change what any single node is asked to do.
    FAN = int(os.environ.get("BASELAYER_MERGE_FAN", "4"))
    MAX_TIERS = 8
    tiers, level, tier_no = [], leaves, 1
    # 🚨 THE MERGE IS VESTIGIAL AND COSTS ABOUT AN HOUR PER LAYER.
    # Themes, singularities and dispositions are all collected MECHANICALLY from the leaves now.
    # The only channel still travelling through the merge is contradictions, and on a 631-leaf
    # tree the tier logs show those arriving as zero at depth with PARSE_FAILED anyway.
    # At FAN=4 a 631-leaf corpus costs 212 sequential model calls per layer to produce nothing
    # load-bearing: 631 -> 158 -> 40 -> 10 -> 3 -> 1, ~18s each, ~1 hour.
    #
    # 🎯 THE DETECTOR WAS BUILT BEFORE THE PATH THAT ACTS ON IT. The guard raises only when leaf
    # payload EXCEEDS the ceiling; below the ceiling it did nothing and the merge ran regardless.
    # So the pipeline correctly knew the merge was unnecessary and ran it anyway. A detector
    # without a corresponding action is half a fix.
    #
    # ⚠️ Contradictions are now collected mechanically too, from the leaves, for the same reason
    # the other channels are: a summarising node is where they get resolved, and they must not be.
    if os.environ.get("BASELAYER_FORCE_MERGE") != "1":
        con = []
        for d in leaves:
            con.extend(d.get("contradictions") or [])
        level = [{"themes": [], "singularities": [], "contradictions": con,
                  "_chunk": "ROOT-direct", "_n": sum(x.get("_n", 0) for x in leaves),
                  "_direct": "merge skipped: no channel is load-bearing above the leaf"}]
        print("MERGE SKIPPED          : %d leaves -> root directly (%d contradictions carried). "
              "Set BASELAYER_FORCE_MERGE=1 to run the tree." % (len(leaves), len(con)))

    while len(level) > 1 and tier_no <= MAX_TIERS:
        tier_no += 1
        groups = [level[i:i + FAN] for i in range(0, len(level), FAN)]
        nxt = []
        for n, g in enumerate(groups, 1):
            p = NODE_PROMPT % (LAYER_DIRECTIVES[a.layer],
                               "\n\n".join(render(x) for x in g), LEAF_SCHEMA)
            d, stop = call_json(cl, a.model, p, 24000, "L%d-%d" % (tier_no, n), stats)
            if d is None:
                d = {"_parse_failed": True}
            # 🚨 INTERIOR NODES FABRICATE TOO, AND ONLY THE LEAF WAS BEING CHECKED. On a
            # 3,688-fact corpus (62 leaves) L2 invented 9 fact ids and 7 singularities on
            # anchors, and 5 ids and 3 singularities on core.
            # The leaf check validates against the chunk it was handed; an interior node's
            # legitimate id set is exactly the union of what ITS INPUTS cited, which is equally
            # computable and was simply never computed. Structurally invisible on a 7-leaf tree
            # where the root merges a single node.
            gi = set()
            for x in g:
                for t in (x.get("themes") or []):
                    gi |= set(t.get("fact_ids") or [])
                for sg in (x.get("singularities") or []):
                    if sg.get("fact_id"):
                        gi.add(sg["fact_id"])
            if gi:
                bad = validate(d, gi)
                if bad:
                    stats.setdefault("node_fabrications", []).append(
                        ("L%d-%d" % (tier_no, n), bad[:4]))
            d["_chunk"] = "L%d-%d" % (tier_no, n)
            d["_n"] = sum(x.get("_n", 0) for x in g)
            nxt.append(d)
            print("  L%d %d/%d themes=%d SING=%d contra=%d%s"
                  % (tier_no, n, len(groups), len(d.get("themes") or []),
                     len(d.get("singularities") or []), len(d.get("contradictions") or []),
                     "  PARSE_FAILED" if d.get("_parse_failed") else ""), flush=True)
        tiers.append(nxt)
        level = nxt
        print("  -- tier %d complete: %d nodes --" % (tier_no, len(level)), flush=True)
    if len(level) > 1:
        raise SystemExit("tree did not converge in %d tiers (%d nodes remain). Raise FAN."
                         % (MAX_TIERS, len(level)))
    root = level[0]

    l2 = tiers[0] if tiers else []

    # 🚨 THE SINGULARITY LANE MUST NOT TRAVEL THROUGH THE TREE. Measured on the predictions layer
    # of a 3,688-fact corpus:
    # 376 leaf singularities reached L2 as 363, and the ROOT TRUNCATED trying to emit them all
    # verbatim -- root empty, survival reported 0%, zero provenance rows. The same run had L2
    # INVENT 2 singularities absent from any leaf.
    #
    # 🎯 THAT IS A DESIGN ERROR AND THE FIX IS TO REMOVE A STEP, NOT ADD ONE. Singularities are
    # INELIGIBLE FOR MERGING BY DEFINITION. Asking a summarising node to relay them is pure
    # cost and pure risk: every hop can paraphrase, invent, or truncate, and the lane's entire
    # value is that the text arrives unchanged. So they are now COLLECTED MECHANICALLY FROM THE
    # LEAVES, deduplicated by fact_id, and attached to the root. No model call touches them
    # after the leaf that chose them.
    #
    # ⚠️ The root still SEES them (they reach it verbatim in the node inputs, which is what
    # reconstitutes the judge holding both a global view and primary evidence). What changed is
    # that it no longer has to REPRODUCE them, which is what the output ceiling could not take.
    # 🚨 PROVENANCE IS A PROPERTY OF EVERY LEVEL, NOT OF THE FINAL ARTIFACT.
    # Citations and provenance are required at every output level: leaves, layers, brief. The
    # first end-to-end run produced a complete, coherent specification containing ZERO resolvable
    # fact ids while every upstream measurement read clean, which is what a chain checked only at
    # its ends looks like when a middle link drops.
    #
    # LEVELS AND THEIR CHECKS:
    #   leaves      themes carry fact_ids, singularities carry fact_id + verbatim, every fact
    #               dispositioned                                          -- checked below
    #   interior    themes must carry ids UPWARD through every merge       -- CHECKED HERE, new.
    #               Verbatim integrity was already checked; ID PROPAGATION WAS NOT, so a theme
    #               could arrive at the root having silently dropped its evidence and look
    #               identical to one that kept it.
    #   root        themes carry ids that resolve to facts a leaf read     -- checked below
    #   package     ids survive stratification                             -- assemble.py
    #   layers      every claim carries the ids it rests on                -- author, strict schema
    #   brief       composed claims carry inherited ids                    -- author, strict schema
    def _ids_at(nodes):
        out = set()
        for n in nodes or []:
            for t in (n.get("themes") or []):
                out.update(t.get("fact_ids") or [])
            for sg in (n.get("singularities") or []):
                if sg.get("fact_id"):
                    out.add(sg["fact_id"])
        return out

    leaf_ids = _ids_at(leaves)
    print("ID PROPAGATION       : leaves cite %d distinct fact ids" % len(leaf_ids))
    for ti, tier_nodes in enumerate(tiers):
        t_ids = _ids_at(tier_nodes)
        bogus = t_ids - leaf_ids
        themes_here = sum(len(n.get("themes") or []) for n in tier_nodes)
        naked = sum(1 for n in tier_nodes for t in (n.get("themes") or [])
                    if not (t.get("fact_ids") or []))
        flag = "  <- THEMES WITH NO IDS" if naked else ""
        print("  L%d  %d ids kept (%.0f%% of leaf ids) | %d of %d themes NAKED%s%s"
              % (ti + 2, len(t_ids), 100.0 * len(t_ids) / max(1, len(leaf_ids)),
                 naked, themes_here, flag,
                 "  | %d INVENTED ABOVE THE LEAF" % len(bogus) if bogus else ""))

    # 🚨 THEMES ARE NOW COLLECTED MECHANICALLY FROM THE LEAVES, LIKE SINGULARITIES.
    # A 3,688-fact corpus (62 leaves) showed the merge doing three things wrong that a 7-leaf
    # tree cannot show: every root came back EMPTY on both fan settings, one tier INVENTED 51
    # themes over its 288 inputs, and interior nodes fabricated ids and singularities. Every
    # channel that survives bypasses the merge; every channel that failed goes through it.
    #
    # 🎯 AND READING THE THEMES SETTLED WHERE THE COLLAPSE BELONGS. Disjoint chunks mean two
    # leaves writing the same theme cite entirely different facts, so no id overlap or lexical
    # key can detect the redundancy: a lexical check said 1%, reading a 26-theme sample found
    # 40-50%. Four leaves each producing a "contract work" theme from four different predicate
    # slices IS the recurrence signal. A merge node collapsing them destroys it, and the root
    # then cannot distinguish a pervasive pattern from a local one.
    #
    # ✅ So the author collapses, because it is the only node with the whole picture and the only
    # place where collapsing does not discard frequency information nothing else records. Each
    # theme carries `seen_in_leaves`, so the author can weigh a theme seen four times against one
    # seen once. The collapse belongs at the author, deliberately, and nowhere earlier.
    theme_lane, seen_theme = [], {}
    for d in leaves:
        for t in (d.get("themes") or []):
            k = (t.get("statement") or "").strip().lower()
            if k in seen_theme:
                seen_theme[k]["seen_in_leaves"] += 1
                seen_theme[k]["fact_ids"] = sorted(set(seen_theme[k].get("fact_ids") or [])
                                                   | set(t.get("fact_ids") or []))
                continue
            e = dict(t); e["seen_in_leaves"] = 1
            seen_theme[k] = e
            theme_lane.append(e)
    relayed = len(root.get("themes") or [])
    root["themes"] = theme_lane
    root["_theme_source"] = "collected mechanically from leaves; no interior node rewrote one"
    print("THEME LANE             : %d collected from leaves (merge had relayed %d)"
          % (len(theme_lane), relayed))


    # 🚨 THE MERGE IS A SCALING MECHANISM AND IT MUST NOT ENGAGE SILENTLY.
    # Themes and singularities are now collected from the leaves, so the author reads leaf output
    # directly and the merge contributes nothing on a corpus whose leaf output FITS. Past that
    # point the merge becomes load-bearing again -- and its defect record at 62 leaves is empty
    # roots, 51 invented themes over 288 inputs, and fabricated ids at interior nodes.
    #
    # 🎯 Merge quality must be evaluated formally BEFORE the merge becomes load-bearing on a
    # given corpus, so this RAISES rather than falling back. A mode change that happens quietly
    # is how most of the failures recorded in this file began.
    #
    # ⚠️ MEASURED, NOT ESTIMATED. A words-per-theme estimate put this at ~200K tokens for a
    # 631-leaf corpus; an estimate 30% low has already misled this project once, which is why the
    # payload is counted rather than guessed. The ceiling is set well below the window because
    # the author's own output and its thinking share that budget.

    lane, seen_sing = [], set()
    for d in leaves:
        for sg in (d.get("singularities") or []):
            fid = sg.get("fact_id")
            if fid and fid not in seen_sing:
                seen_sing.add(fid)
                lane.append(sg)
    carried = {sg.get("fact_id") for sg in (root.get("singularities") or [])}
    root["singularities"] = lane

    # 🚨 THIS BLOCK MUST STAY BELOW ITS OWN INPUT. It previously read `lane` twenty-one lines
    # before `lane` was bound, so every run raised UnboundLocalError into the broad except
    # below and printed the warning instead. The guard that decides when the merge becomes
    # load-bearing at scale had therefore never executed once, while printing a line on every
    # run that operators learned to read as benign.
    try:
        import anthropic as _a
        payload = json.dumps({"themes": theme_lane, "singularities": lane})
        n_tok = _a.Anthropic().messages.count_tokens(
            model=a.model, messages=[{"role": "user", "content": payload}]).input_tokens
        CEIL = int(os.environ.get("BASELAYER_LEAF_PAYLOAD_CEILING", "400000"))
        print("LEAF PAYLOAD           : %d tokens (ceiling %d, direct path %s)"
              % (n_tok, CEIL, "OK" if n_tok <= CEIL else "EXCEEDED"))
        if n_tok > CEIL:
            raise SystemExit(
                "LEAF PAYLOAD %d TOKENS EXCEEDS THE %d CEILING. The author can no longer read "
                "leaf output directly, so the MERGE becomes load-bearing on this corpus. Its "
                "measured defects at 62 leaves were empty roots, 51 themes invented over 288 "
                "inputs, and fabricated ids at interior nodes. Evaluate merge quality on THIS "
                "corpus before proceeding: compare theme counts per tier against the sum of the "
                "tier below, and check ids and singularities at every level against their "
                "inputs. Do not raise the ceiling to get past this." % (n_tok, CEIL))
    except SystemExit:
        raise
    except Exception as e:
        print("WARNING: could not measure leaf payload (%s). The direct-path assumption is "
              "UNVERIFIED for this run." % e)
    root["_lane_source"] = "collected mechanically from leaves; no interior node relayed them"
    root["_root_relayed_before_override"] = sorted(carried)[:50]
    print("SINGULARITY LANE       : %d collected from leaves (root had relayed %d)"
          % (len(lane), len(carried)))

    # 🚨 AN EMPTY ROOT IS A FAILED RUN, NOT A RESULT. Checked HERE, after mechanical collection,
    # because the merged root is empty BY DESIGN now: themes and singularities are collected from
    # the leaves, so what matters is what the root CARRIES, not what the merge relayed.
    # ⚠️ Placing this before collection was an ordering bug that raised on every healthy run.
    if not (root.get("themes") or []) and not (root.get("singularities") or []):
        raise SystemExit(
            "ROOT CARRIES NOTHING: %d themes and %d singularities were collected from %d leaves "
            "and neither reached the root. This is a collection failure, not a thin corpus."
            % (len(theme_lane), len(lane), len(leaves)))

    tin, tout = stats["in"], stats["out"]

    # 🚨 THE STAMP BLOCK WAS DELETED BY THE RECURSIVE-MERGE PATCH AND NOTHING CAUGHT IT.
    # The patch replaced everything between the old L2 loop and `tree = {...}`, which happened
    # to span this. The failure surfaced only at the very END of a run -- after every leaf was
    # paid for -- as `NameError: name 'stamp' is not defined`. A whole tree's spend, lost on a
    # variable. That is what editing by span rather than by anchor costs, and it is why the
    # syntax check passed: the name is only unbound at runtime.
    import hashlib
    ch = hashlib.sha256(("|".join(r[0] for r in rows)).encode()).hexdigest()[:16]
    ph = hashlib.sha256((LEAF_PROMPT + NODE_PROMPT + LEAF_SCHEMA
                         + LAYER_DIRECTIVES[a.layer]).encode()).hexdigest()[:16]
    codesha = hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:12]
    rid = hashlib.sha256(("%s|%s|%s|%s|%d|%d|%s|%d"
                          % (ch, ph, a.model, a.partition, a.max_facts, a.seed, a.layer,
                             a.limit_chunks)).encode()).hexdigest()[:12]
    stamp = {"run_id": rid, "layer": a.layer, "model": a.model, "partition": a.partition,
             "chunk_size": a.max_facts, "seed": a.seed, "corpus_hash": ch, "prompt_hash": ph,
             "code_sha": codesha, "code_path": os.path.abspath(__file__),
             "facts_total": len(rows), "chunks": len(chunks),
             "limit_chunks": a.limit_chunks, "PARTIAL_RUN": bool(a.limit_chunks),
             "tiers": len(tiers), "directive": LAYER_DIRECTIVES[a.layer],
             "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print("STAMP run_id=%s layer=%s corpus=%s prompt=%s code=%s tiers=%d"
          % (rid, a.layer, ch, ph, codesha, len(tiers)))

    tree = {"stamp": stamp, "leaves": leaves, "level2": l2, "tiers": tiers, "root": root,
            "usage": {"in": tin, "out": tout, "cost_usd": round(_cost(a.model, tin, tout), 2)},
            "facts_total": len(rows), "chunks": len(chunks), "seconds": round(time.time() - t0)}
    json.dump(tree, open(a.out, "w", encoding="utf-8"), indent=1)

    # 🚨 THE TREE IS THE DELIVERABLE, NOT A BUILD ARTIFACT, AND IT WAS BEING WRITTEN WHEREVER
    # --out HAPPENED TO POINT. This architecture's central claim is that every intermediate is
    # retained because THE TRACE IS THE DELIVERABLE: the tree is what makes any claim in a
    # layer checkable, what the handoff package is assembled from, and what a later run diffs
    # against. Leaving its location to a caller's scratch path meant the audit record could be
    # deleted while the layer it justifies survived -- provenance outliving its own evidence.
    #
    # It now ALSO lands in the corpus directory, beside the other run outputs, named by layer and
    # run_id so generations accumulate rather than overwrite. The --out copy stays for convenience.
    try:
        # THE TWO-LEVELS-UP WALK ASSUMES <corpus>/data/database/memory.db AND WRITES OUTSIDE
        # THE USER'S DIRECTORY WHEN THAT DOES NOT HOLD. With the quickstart's `--db facts.db`
        # in the current directory, dirname twice lands on the PARENT of the working directory,
        # so an outside user's first run silently created a folder above where they were
        # standing. Only take the walk when the layout that justifies it is actually present.
        _dbdir = os.path.dirname(os.path.abspath(a.db))
        if os.path.basename(_dbdir) == "database":
            home = os.path.join(os.path.dirname(_dbdir), "distillation")
        else:
            home = os.path.join(_dbdir, "distillation")
        os.makedirs(home, exist_ok=True)
        canon = os.path.join(home, "%s_%s.json" % (a.layer, rid))
        json.dump(tree, open(canon, "w", encoding="utf-8"), indent=1)
        # A pointer to the newest tree per layer, so consumers do not guess at run ids.
        json.dump({"layer": a.layer, "run_id": rid, "tree": os.path.basename(canon),
                   "generated_utc": stamp["generated_utc"], "facts": len(rows),
                   "chunks": len(chunks), "tiers": len(tiers)},
                  open(os.path.join(home, "LATEST_%s.json" % a.layer), "w",
                       encoding="utf-8"), indent=1)
        print("tree archived          : %s" % canon)
    except Exception as e:
        print("WARNING: tree NOT archived to the corpus (%s). The --out copy is the only "
              "record and it may be scratch." % e)

    disp = {}
    for d in leaves:
        disp.update(d.get("dispositions") or {})
    scope = {i for d in leaves for i in d["_ids"]}
    sing_l1 = sum(len(d.get("singularities") or []) for d in leaves)
    sing_l2 = sum(len(d.get("singularities") or []) for d in l2)
    sing_rt = len(root.get("singularities") or [])
    print("\n=== AUDIT ===")
    print("facts in scope         : %d" % len(scope))
    print("facts with disposition : %d (%.1f%%)   <- the 'I looked' claim"
          % (len(set(disp) & scope), 100.0 * len(set(disp) & scope) / max(1, len(scope))))
    print("disposition breakdown  : %s" % dict(Counter(disp.values())))
    # NOT "survival". On the direct path the root lane is a mechanical copy of the deduped leaf
    # lane, so loss is impossible and this ratio measures cross-leaf DUPLICATION. The ledger was
    # renamed to sing_dedup_pct; this line said "survival" for another commit and contradicted
    # both the ledger and the README from the output every quickstart user reads.
    _mech = not os.environ.get("BASELAYER_FORCE_MERGE")
    print("singularities  L1=%d -> L2=%d -> root=%d   (dedup %.0f%%%s)"
          % (sing_l1, sing_l2, sing_rt, 100.0 * sing_rt / max(1, sing_l1),
             ", mechanical copy: cannot register loss" if _mech else ""))
    print("contradictions L1=%d -> L2=%d -> root=%d"
          % (sum(len(d.get("contradictions") or []) for d in leaves),
             sum(len(d.get("contradictions") or []) for d in l2),
             len(root.get("contradictions") or [])))
    print("PARSE: failed-first-try %s | repaired %s | STILL BROKEN %s | truncated %s" %
          (stats["parse_fail"] or "none", stats["repaired"] or "none",
           stats["parse_fail_final"] or "NONE", stats["truncated"] or "none"))
    print("SCHEMA: violations %s | repaired %s | STILL INVALID %s" %
          ([x[0] for x in stats["schema_fail"]] or "none",
           stats["schema_repaired"] or "none", stats["schema_fail_final"] or "NONE"))
    for lbl, why in stats["schema_fail"][:4]:
        print("   %s -> %s" % (lbl, "; ".join(why)[:120]))
    if stats["parse_fail_final"]:
        print("  !! A node is EMPTY because it could not be parsed, NOT because it dropped "
              "content. Any survival number below is VOID for those nodes.")
    # PROVENANCE, self-enforced: can a node cite an id that was never in its chunk?
    # A model can hold this invariant by habit across many runs and still break it once.
    # Check it here rather than assume it, because a citation that does not resolve is a
    # provenance chain that verifies against nothing.
    _a = audit_citations(leaves)
    cited, bad, stripped = _a["cited"], _a["survived_stripper"], _a["stripped"]
    fab, attempted, clean_pct = _a["fabricated"], _a["attempted"], _a["clean_pct"]
    print("leaf citations         : %d cited, %d fabricated and STRIPPED (%.2f%% clean of %d "
          "attempted)" % (cited, fab, clean_pct, attempted))
    print("   dispositions stripped: %d foreign" % stripped["dispositions"])
    if bad:
        print("   INVARIANT BROKEN: %d fabricated ids SURVIVED the stripper" % bad)
    # Did the singularity lane carry text VERBATIM, or did it paraphrase?
    txtof = {r[0][:8]: r[1] for r in rows}
    ver = vok = 0
    for d in leaves:
        for s in (d.get("singularities") or []):
            fid = s.get("fact_id")
            if fid in txtof:
                ver += 1
                vok += (s.get("verbatim", "").strip() == txtof[fid].strip())
    print("singularity verbatim   : %d of %d exact (%.0f%%)  <- LEAF lane integrity"
          % (vok, ver, 100.0 * vok / max(1, ver)))
    # 🚨 THE AUDIT USED TO STOP AT THE LEAF WHILE EVERY CLAIM WAS ABOUT THE TREE.
    # The root could have paraphrased every singularity and each number above would still read
    # clean, because nothing compared an interior node's text to the database. "Survival" was a
    # COUNT and "verbatim exact" was a LEAF measurement, printed together as if they were one
    # guarantee. The lane's whole value is that text arrives unparaphrased AT THE ROOT.
    l1_sing_ids = {s.get("fact_id") for d in leaves for s in (d.get("singularities") or [])}
    for lvl, nodes in (("L2", l2), ("ROOT", [root])):
        n_ok = n_chk = n_invented = 0
        for d in nodes:
            for s in (d.get("singularities") or []):
                fid = s.get("fact_id")
                if fid not in l1_sing_ids:
                    n_invented += 1          # not carried up: conjured at this level
                if fid in txtof:
                    n_chk += 1
                    n_ok += (s.get("verbatim", "").strip() == txtof[fid].strip())
        print("  %-4s verbatim %d of %d exact | %d singularities NOT PRESENT AT L1%s"
              % (lvl, n_ok, n_chk, n_invented,
                 "  <- INVENTED ABOVE THE LEAF" if n_invented else ""))
    print("cost $%.2f  in=%d out=%d  %ds" % (tree["usage"]["cost_usd"], tin, tout, tree["seconds"]))

    # PROVENANCE PERSISTENCE + THE ROOT-CITATION CHECK.
    #
    # 🚨 THE CHAIN EXISTED AND WAS UNREACHABLE. Every theme carries fact_ids and every
    # singularity carries fact_id plus verbatim text, but `layer_claim_provenance` appeared
    # ZERO times in this package, so any claim-tracing query returned empty for a distilled
    # layer. The same defect had already been fixed on the path this one replaced, and it was
    # reproduced here: fixing a defect on one code path does not fix it on its sibling.
    #
    # 🎯 AND THE CHECK THAT CANNOT BE RECONSTRUCTED LATER: the leaf audit proves a cited id
    # belonged to its own CHUNK. Nothing proved the ROOT did not invent one. Once the tree is
    # written the leaf sets are still on disk, but only this pass knows which ids were actually
    # READ, so the verdict is computed here and stamped rather than left inferable.
    leaf_ids = {i for d in leaves for i in (d.get("_ids") or [])}
    root_cited, root_bad = set(), set()
    for t in (root.get("themes") or []):
        for fid in (t.get("fact_ids") or []):
            (root_cited if fid in leaf_ids else root_bad).add(fid)
    for sg in (root.get("singularities") or []):
        fid = sg.get("fact_id")
        if fid:
            (root_cited if fid in leaf_ids else root_bad).add(fid)
    print("ROOT citations         : %d resolve to facts a leaf actually read, %d DO NOT%s"
          % (len(root_cited), len(root_bad),
             "  <- INVENTED ABOVE THE LEAF" if root_bad else ""))
    if root_bad:
        print("   unresolved: %s" % sorted(root_bad)[:8])

    prov_rows = 0
    if a.write_provenance:
        full = {r[0][:8]: r[0] for r in rows}
        try:
            wc = sqlite3.connect(a.db)
            wc.execute("""CREATE TABLE IF NOT EXISTS layer_claim_provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT, layer_name TEXT, claim_id TEXT,
                claim_text TEXT, fact_id TEXT, link_method TEXT, similarity_score REAL,
                rank_in_claim INTEGER, layer_version TEXT, cycle_id TEXT, created_at REAL)""")
            wc.execute("DELETE FROM layer_claim_provenance WHERE layer_name=? AND "
                       "link_method='distillation'", (a.layer.upper(),))
            items = ([("T%d" % i, t.get("statement", ""), t.get("fact_ids") or [])
                      for i, t in enumerate(root.get("themes") or [], 1)]
                     + [("S%d" % i, sg.get("verbatim", ""), [sg.get("fact_id")])
                        for i, sg in enumerate(root.get("singularities") or [], 1)])
            now = time.time()
            for cid, ctext, fids in items:
                for rank, fid in enumerate([f for f in fids if f], 1):
                    # Resolve the 8-char prefix to the full id, or the row cannot be joined.
                    resolved = full.get(fid, fid if fid in full.values() else None)
                    if not resolved:
                        continue
                    wc.execute(
                        "INSERT INTO layer_claim_provenance (layer_name, claim_id, claim_text,"
                        " fact_id, link_method, rank_in_claim, layer_version, cycle_id,"
                        " created_at) VALUES (?,?,?,?,'distillation',?,?,?,?)",
                        # 🚨 TRUNCATED THE AUDIT RECORD ITSELF. ctext[:500] cut the claim text written into
                        # layer_claim_provenance. It does not bound what the model
                        # sees, which makes it worse in a different way: the trace
                        # a reader follows was stored abridged.
                        (a.layer.upper(), cid, ctext, resolved, rank, rid, rid, now))
                    prov_rows += 1
            wc.commit(); wc.close()
            print("provenance written     : %d rows (link_method='distillation') -> %s"
                  % (prov_rows, os.path.basename(a.db)))
        except Exception as e:
            print("provenance WRITE FAILED: %s  <- the chain is in the tree but unreachable"
                  % e)

    # THE RUN LEDGER. Every tree is a VERSION, and the diffs between versions are what the
    # diff daemon reads. Ad hoc output files are not a record: a comparison you cannot
    # reconstruct the parameters of is an anecdote. One append-only row per run, carrying
    # everything needed to say WHAT produced this tree and WHAT it did, so a later session
    # can compare two trees without re-deriving how either was made.
    row = {
        "run": os.path.basename(a.out), "layer": a.layer, "run_id": rid,
        "corpus_hash": ch, "prompt_hash": ph, "code_sha": codesha,
        "corpus": os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(a.db)))),
        "partition": a.partition, "chunk_size": a.max_facts, "seed": a.seed,
        "model": a.model, "facts": len(rows), "chunks": len(chunks),
        "disposition_pct": round(100.0 * len(set(disp) & scope) / max(1, len(scope)), 1),
        "dispositions": dict(Counter(disp.values())),
        "sing_l1": sing_l1, "sing_l2": sing_l2, "sing_root": sing_rt,
        # `sing_survival_pct` REMOVED. On the direct path the root singularity lane is a
        # mechanical copy of the deduped leaf lane, so loss is impossible and the number was
        # bounded at 100% by construction. Its sub-100 values were measuring cross-leaf
        # DUPLICATION, not survival. The raw counts above say everything it said, honestly.
        "sing_dedup_pct": round(100.0 * sing_rt / max(1, sing_l1), 1),
        "contra_l1": sum(len(d.get("contradictions") or []) for d in leaves),
        "contra_root": len(root.get("contradictions") or []),
        # Contradictions are copied wholesale to root on the direct path, so l1 == root is
        # expected and is NOT evidence of survival through a merge.
        "contra_carried_is_mechanical": not os.environ.get("BASELAYER_FORCE_MERGE"),
        # RATE OF FABRICATION ATTEMPTS, measured pre-strip. `bad` is the post-strip invariant
        # and belongs beside it as a separate field, not folded into the rate.
        "citations_attempted": cited + stripped["theme_ids"] + stripped["singularities"],
        "citations_fabricated_stripped": stripped["theme_ids"] + stripped["singularities"],
        "dispositions_foreign_stripped": stripped["dispositions"],
        "citations_clean_pct": round(clean_pct, 2),
        "citations_survived_stripper": bad,
        "verbatim_exact_pct": round(100.0 * vok / max(1, ver), 1),
        # The verbatim check can only compare ids that RESOLVE, so unresolvable ids are
        # excluded from its denominator rather than failed. Report that population instead of
        # letting it vanish: shipped rows carried 7- and 9-character ids while reading 100.0.
        "verbatim_checked": ver,
        "verbatim_unresolvable": sum(
            1 for d in leaves for sg in (d.get("singularities") or [])
            if sg.get("fact_id") and sg["fact_id"] not in txtof),
        "parse_failures": sum(1 for d in leaves if d.get("_parse_failed")),
        "root_themes": len(root.get("themes") or []),
        "root_singularity_ids": sorted(s.get("fact_id") for s in (root.get("singularities") or [])
                                       if s.get("fact_id")),
        # `root_citations_resolved` was forced: root themes and singularities are collected
        # mechanically from post-strip leaves, so every root id is by construction inside some
        # leaf's id set and root_bad was empty on every path. Kept as an INVARIANT (must be 0),
        # renamed so it no longer reads as a quality measurement it cannot make.
        "root_citations_counted": len(root_cited),
        "root_citations_INVARIANT_VIOLATIONS": sorted(root_bad)[:10],
        "root_invariant_is_mechanical": not os.environ.get("BASELAYER_FORCE_MERGE"),
        "provenance_rows": prov_rows,
        "cost_usd": tree["usage"]["cost_usd"], "in": tin, "out": tout,
        "seconds": tree["seconds"], "tree_path": os.path.abspath(a.out),
    }
    # THE LEDGER FOLLOWS THE ARCHIVE, NOT --out. Keyed to --out, running the quickstart from a
    # clone appended the user's rows to the distill_runs.jsonl SHIPPED IN THIS REPO: their run
    # history mixed into the reference data, and a `git diff` full of their corpus. The archive
    # directory is where the rest of the trace already lives.
    try:
        led = os.path.join(home, "distill_runs.jsonl")
    except NameError:
        led = os.path.join(os.path.dirname(os.path.abspath(a.out)), "distill_runs.jsonl")
    with open(led, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print("ledger -> %s" % led)



if __name__ == "__main__":
    main()
